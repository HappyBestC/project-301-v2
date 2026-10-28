import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest

from core301.agent_chain.scheduling import LLMSchedulingProvider
from core301.agent_chain.treatment import LLMTreatmentProvider, PROMPT_PATH, build_treatment_input, template_decisions
from core301.dispatch.providers import LLMDispatchProvider
from core301.dispatch.minimal import api


CONFIG = SimpleNamespace(model='test-requested-model', base_url='https://test.invalid', api_key='private-test-key')


def client_mock(monkeypatch, raw, *, error=None):
    import openai
    calls, settings = [], []

    class Response:
        model = 'test-returned-model'
        usage = SimpleNamespace(model_dump=lambda: {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30})
        choices = [SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='stop')]

        def model_dump(self, **kwargs):
            return {'model': self.model, 'usage': self.usage.model_dump(), 'choices': [
                {'message': {'content': raw}, 'finish_reason': 'stop'}]}

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


def treatment_provider():
    provider = LLMTreatmentProvider.__new__(LLMTreatmentProvider)
    provider.config, provider.called = CONFIG, set()
    return provider


def scheduling_provider():
    provider = LLMSchedulingProvider.__new__(LLMSchedulingProvider)
    provider.provider = LLMDispatchProvider.__new__(LLMDispatchProvider)
    provider.provider._config = CONFIG
    return provider


def test_treatment_sdk_audits_original_response_usage_and_prompt_sha(chain_data, tmp_path, monkeypatch):
    cases, mapping, _, _ = chain_data
    payload = build_treatment_input(cases[0], mapping)
    raw = template_decisions()['P01']
    calls, settings = client_mock(monkeypatch, raw)
    provider = treatment_provider()
    assert asyncio.run(provider.propose(payload, audit_dir=tmp_path)) == raw
    assert len(calls) == 1 and calls[0]['max_tokens'] == 1200
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
    with pytest.raises(RuntimeError, match='LLM_CALL_FAILED:RuntimeError'):
        asyncio.run(provider.propose(payload, audit_dir=tmp_path))
    assert len(calls) == 1
    assert api.read(tmp_path / 'llm_error.json')['retry_attempted'] is False
    assert api.read(tmp_path / 'response_metadata.json')['usage'] is None
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


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
