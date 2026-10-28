"""Required baseline parity and fixed-payload checks; discrepancies fail openly."""
import asyncio

import pytest

from core301.agent_chain.bridge import treatment_payload
from core301.agent_chain.scheduling import REPLAY_PATH, ReplaySchedulingProvider
from core301.agent_chain.treatment import TemplateTreatmentProvider, admit, build_treatment_input
from core301.dispatch.minimal import api
from core301.dispatch.minimal.validation import validate_schedule
from core301.pulse.v2.protocol_book import ALLOWED_ACTIONS, OPEN_INJURIES
from core301.runtime.v2_1.adapters import action_payload


def converted_cases(tmp_path):
    _, mapping = api.load_config()
    cases = api.load_cases()
    provider = TemplateTreatmentProvider()
    for case in cases:
        payload = build_treatment_input(case, mapping)
        raw = asyncio.run(provider.propose(payload, audit_dir=tmp_path / case['patient_id']))
        _, plans = admit(raw, payload, mapping, plan_status=provider.plan_status)
        case['candidate_plans'] = plans
    return cases


@pytest.mark.parametrize('patient_id', [f'P{i:02}' for i in range(1, 17)])
def test_template_candidates_equal_load_cases_field_by_field(tmp_path, patient_id):
    actual = next(c for c in converted_cases(tmp_path) if c['patient_id'] == patient_id)
    expected = next(c for c in api.load_cases() if c['patient_id'] == patient_id)
    assert actual['candidate_plans'] == expected['candidate_plans']


def test_template_replay_matches_bundled_dispatch_input(tmp_path):
    context = api.build_input(*api.load_config(), converted_cases(tmp_path),
                              horizon_min=120.0, observation_time_min=60.0)
    baseline = api.read(REPLAY_PATH.with_name('dispatch_input.json'))
    assert context['patients'] == baseline['patients']
    proposal = asyncio.run(ReplaySchedulingProvider().propose(
        context, feedback=None, previous_response=None, audit_dir=tmp_path))
    result = validate_schedule(context, proposal['schedule'])
    assert result['conflicts'] == []
    assert result['scheduled_patients'] == 16


@pytest.mark.parametrize('injury_type,kind', [(injury, kind)
    for injury in OPEN_INJURIES for kind in sorted(ALLOWED_ACTIONS[injury])])
def test_open_injury_payloads_identical_across_both_sources(injury_type, kind):
    spec = next(s for s in api.read(api.DATASET / 'patient_specs.json') if s['injury']['injury_type'] == injury_type)
    _, mapping = api.load_config()
    target = {'patient_id': spec['patient_id']}
    target_kind = mapping['actions'][kind]['target_kind']
    if target_kind in ('side', 'compartment'):
        target[target_kind] = spec['injury'][target_kind]
    payload = treatment_payload(spec, {'action_type': kind, 'target': target})
    assert payload == action_payload(kind, None)
