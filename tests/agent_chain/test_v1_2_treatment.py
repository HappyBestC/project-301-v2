import asyncio
import json

import pytest

from core301.agent_chain.nodes import Nodes, Providers
from core301.agent_chain.runner import run_chain
from core301.agent_chain.scheduling import FakeSchedulingProvider
from core301.agent_chain.treatment import FakeTreatmentProvider, template_decisions
from core301.dispatch.minimal import api
from tests.agent_chain.test_graph import fast_execute


@pytest.mark.parametrize('response,finish,code', [
    ('{}', 'length', 'OUTPUT_TRUNCATED'),
    ('', 'length', 'OUTPUT_TRUNCATED'),
    ('', 'stop', 'EMPTY_RESPONSE'),
    (RuntimeError('secret-request-detail'), None, 'CALL_FAILED'),
    ('{broken', 'stop', 'JSON_INVALID'),
    ('{"patient_id":NaN}', 'stop', 'JSON_INVALID'),
    ('{}', 'stop', 'ADMISSION_REJECTED'),
    ('{"patient_id":"P01","patient_id":"P02"}', 'stop', 'ADMISSION_REJECTED'),
])
def test_fake_provider_failure_codes_preserve_safe_details(chain_data, tmp_path, response, finish, code):
    cases, mapping, _, _ = chain_data
    responses = template_decisions()
    responses['P01'] = response
    treatment = FakeTreatmentProvider(responses, finish_reasons={'P01': finish})
    nodes = Nodes(Providers(treatment, FakeSchedulingProvider([])), {})
    state = {'cases': cases, 'mapping': mapping, 'run_dir': str(tmp_path), 'scenario': 'run_001'}
    result = asyncio.run(nodes.treatment(state))
    reason = result['excluded_patients']['P01']
    admission = api.read(tmp_path / 'treatment/P01/admission.json')
    assert reason['reason_code'] == code and admission['error'] == reason
    assert not admission['admitted'] and len(result['excluded_patients']) == 1
    if code == 'CALL_FAILED':
        assert reason == {'reason_code': code, 'error_type': 'RuntimeError', 'status_code': None}
        assert 'secret-request-detail' not in json.dumps(result)
    if code in ('JSON_INVALID', 'ADMISSION_REJECTED'):
        assert reason['detail']


@pytest.mark.parametrize('value', [255, 32769, True, 8192.0, '8192'])
def test_runner_rejects_token_limit_before_creating_run(tmp_path, value):
    with pytest.raises(ValueError, match='256 and 32768'):
        asyncio.run(run_chain('offline', 'invalid', root=tmp_path, treatment_max_tokens=value))
    assert not list(tmp_path.iterdir())


def test_runner_records_token_limit_in_manifest(chain_data, tmp_path):
    _, _, _, schedule = chain_data
    providers = Providers(FakeTreatmentProvider(template_decisions()), FakeSchedulingProvider([schedule]), fast_execute)
    asyncio.run(run_chain('offline', 'tokens', root=tmp_path, providers=providers, treatment_max_tokens=4096))
    assert api.read(tmp_path / 'tokens/manifest.json')['parameters']['treatment_max_tokens'] == 4096
