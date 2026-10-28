import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest

from core301.agent_chain.scheduling import LLMSchedulingProvider
from core301.agent_chain.treatment import (LLMTreatmentProvider, PROMPT_PATH, TreatmentFailure,
                                          build_treatment_input, template_decisions)
from core301.dispatch.providers import LLMDispatchProvider
from core301.dispatch.minimal import api


CONFIG = SimpleNamespace(model='test-requested-model', base_url='https://test.invalid', api_key='private-test-key')


def client_mock(monkeypatch, raw, *, error=None, finish_reason='stop'):
    import openai
    calls, settings = [], []

    class Response:
        model = 'test-returned-model'
        usage = SimpleNamespace(model_dump=lambda: {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30})
        choices = [SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason=finish_reason)]

        def model_dump(self, **kwargs):
            return {'model': self.model, 'usage': self.usage.model_dump(), 'choices': [
                {'message': {'content': raw}, 'finish_reason': finish_reason}]}

    class Client:
        def __init__(self, **options):
            settings.append(options)
            self.chat = SimpleNamespace(completions=self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def create(self, **request):
            calls.append(request)
            if error:
                raise error
            return Response()

    monkeypatch.setattr(openai, 'AsyncOpenAI', Client)
    return calls, settings


def treatment_provider(max_tokens=8192):
    provider = LLMTreatmentProvider.__new__(LLMTreatmentProvider)
    provider.config, provider.called = CONFIG, set()
    provider.max_tokens = max_tokens
    return provider


def scheduling_provider():
    provider = LLMSchedulingProvider.__new__(LLMSchedulingProvider)
    provider.provider = LLMDispatchProvider.__new__(LLMDispatchProvider)
    provider.provider._config = CONFIG
    return provider


@pytest.mark.parametrize('max_tokens', [8192, 256, 4096, 32768])
def test_treatment_sdk_audits_original_response_usage_and_prompt_sha(chain_data, tmp_path, monkeypatch, max_tokens):
    cases, mapping, _, _ = chain_data
    payload = build_treatment_input(cases[0], mapping)
    raw = template_decisions()['P01']
    calls, settings = client_mock(monkeypatch, raw)
    provider = treatment_provider(max_tokens)
    assert asyncio.run(provider.propose(payload, audit_dir=tmp_path)) == raw
    assert len(calls) == 1 and calls[0]['max_tokens'] == max_tokens
    assert settings[0]['max_retries'] == 0 and settings[0]['timeout'] == 60
    request = api.read(tmp_path / 'llm_request.json')
    metadata = api.read(tmp_path / 'response_metadata.json')
    assert request['prompt_sha256'] == hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    assert metadata['requested_model'] == CONFIG.model and metadata['returned_model'] == 'test-returned-model'
    assert metadata['usage'] == {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
    assert (tmp_path / 'response.txt').read_text() == raw
    assert api.read(tmp_path / 'llm_response.json')['choices'][0]['message']['content'] == raw
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())
    with pytest.raises(RuntimeError, match='One request'):
        asyncio.run(provider.propose(payload, audit_dir=tmp_path))
    assert len(calls) == 1


def test_treatment_failure_has_no_retry_and_no_exception_secret(chain_data, tmp_path, monkeypatch):
    cases, mapping, _, _ = chain_data
    calls, _ = client_mock(monkeypatch, '', error=RuntimeError('private-test-key'))
    provider = treatment_provider()
    payload = build_treatment_input(cases[0], mapping)
    with pytest.raises(TreatmentFailure, match='CALL_FAILED') as error:
        asyncio.run(provider.propose(payload, audit_dir=tmp_path))
    assert error.value.reason == {'reason_code': 'CALL_FAILED', 'error_type': 'RuntimeError', 'status_code': None}
    assert len(calls) == 1
    assert api.read(tmp_path / 'llm_error.json')['retry_attempted'] is False
    assert api.read(tmp_path / 'response_metadata.json')['usage'] is None
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


@pytest.mark.parametrize('raw,finish,code', [('', 'length', 'OUTPUT_TRUNCATED'),
    ('{}', 'length', 'OUTPUT_TRUNCATED'), (' ', 'stop', 'EMPTY_RESPONSE')])
def test_treatment_failure_uses_sdk_finish_reason(chain_data, tmp_path, monkeypatch, raw, finish, code):
    cases, mapping, _, _ = chain_data
    calls, _ = client_mock(monkeypatch, raw, finish_reason=finish)
    with pytest.raises(TreatmentFailure) as error:
        asyncio.run(treatment_provider().propose(build_treatment_input(cases[0], mapping), audit_dir=tmp_path))
    assert error.value.reason['reason_code'] == code and len(calls) == 1
    assert api.read(tmp_path / 'response_metadata.json')['finish_reason'] == finish
    assert (tmp_path / 'response.txt').read_text() == raw


def test_treatment_constructor_default_and_bounds(monkeypatch):
    from core301.agent import llm_config
    monkeypatch.setattr(llm_config, 'load_llm_config', lambda root: CONFIG)
    assert LLMTreatmentProvider().max_tokens == 8192
    for value in (255, 32769, True, 8192.0, '8192'):
        with pytest.raises(ValueError, match='256 and 32768'):
            LLMTreatmentProvider(value)


def test_scheduling_reuses_existing_sdk_path_with_feedback_and_audit(chain_data, tmp_path, monkeypatch):
    _, _, context, schedule = chain_data
    raw = json.dumps(schedule)
    calls, settings = client_mock(monkeypatch, raw)
    feedback = {'round': 1, 'conflicts': [{'code': 'test'}]}
    result = asyncio.run(scheduling_provider().propose(context, feedback=feedback,
                        previous_response='old raw response', audit_dir=tmp_path))
    assert len(calls) == 1 and settings[0]['max_retries'] == 0 and settings[0]['timeout'] == 180
    assert calls[0]['messages'][-2] == {'role': 'assistant', 'content': 'old raw response'}
    assert json.loads(calls[0]['messages'][-1]['content']) == {'validator_feedback': feedback}
    assert result['schedule'] == schedule and not result['validation']['conflicts']
    metadata = api.read(tmp_path / 'response_metadata.json')
    assert metadata['prompt_sha256'] and metadata['usage']['total_tokens'] == 30
    assert metadata['requested_model'] == CONFIG.model and metadata['returned_model'] == 'test-returned-model'
    assert (tmp_path / 'response.txt').read_text() == raw
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_scheduling_request_failure_is_audited_without_retry(chain_data, tmp_path, monkeypatch):
    _, _, context, _ = chain_data
    calls, settings = client_mock(monkeypatch, '', error=RuntimeError('private-test-key'))
    with pytest.raises(RuntimeError):
        asyncio.run(scheduling_provider().propose(context, feedback=None,
                    previous_response=None, audit_dir=tmp_path))
    assert len(calls) == 1 and settings[0]['max_retries'] == 0
    assert api.read(tmp_path / 'llm_error.json')['retry_attempted'] is False
    assert api.read(tmp_path / 'llm_request_metadata.json')['prompt_sha256']
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


@pytest.mark.parametrize('raw', ['', '{broken', '{"number":NaN}'])
def test_malformed_model_content_is_a_conflict_not_request_failure_or_mismatch(
        chain_data, tmp_path, monkeypatch, raw):
    from tests.agent_chain.test_graph import run
    _, _, context, schedule = chain_data
    client_mock(monkeypatch, raw)
    audit_dir = tmp_path / 'provider'
    result = asyncio.run(scheduling_provider().propose(
        context, feedback=None, previous_response=None, audit_dir=audit_dir))
    summary, provider, directory = run(tmp_path, [result, schedule])
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'full'
    assert len(provider.calls) == 2 and 'schedule_error' not in summary
    assert provider.calls[1]['feedback']['conflicts'][0]['code'] == 'MODEL_JSON_INVALID'
    assert not (directory / 'schedule/attempt_01/error.json').exists()


def test_treatment_request_error_preserves_original_status_code(chain_data, tmp_path, monkeypatch):
    class ServiceFailure(RuntimeError):
        status_code = 503
    cases, mapping, _, _ = chain_data
    calls, _ = client_mock(monkeypatch, '', error=ServiceFailure('private-test-key'))
    with pytest.raises(TreatmentFailure) as error:
        asyncio.run(treatment_provider().propose(build_treatment_input(cases[0], mapping), audit_dir=tmp_path))
    assert error.value.reason == {'reason_code': 'CALL_FAILED', 'error_type': 'ServiceFailure', 'status_code': 503}
    assert len(calls) == 1
