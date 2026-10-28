"""Scheduling backend boundary; all results are independently checked by the graph."""
import copy
import json
from pathlib import Path
from typing import Protocol

from core301.dispatch.minimal import api
from core301.paths import PROJECT_ROOT
from .audit import safe_error, sha256, write_json
from .scenarios import scenario_paths

REPLAY_PATH = scenario_paths('run_001')['replay_schedule']


class SchedulingProvider(Protocol):
    async def propose(self, dispatch_input: dict, *, feedback: dict | None,
                      previous_response: str | None, audit_dir: Path) -> dict: ...


class ReplaySchedulingProvider:
    def __init__(self, path: Path = REPLAY_PATH):
        if path is None:
            raise ValueError('Scenario has no replay schedule')
        self.path = Path(path)

    async def propose(self, dispatch_input, *, feedback, previous_response, audit_dir):
        raw = self.path.read_text()
        return {'schedule': api.read(self.path), 'raw_response': raw,
                'metadata': {'source': str(self.path), 'source_sha256': sha256(raw.encode()), 'model_called': False}}


class FakeSchedulingProvider:
    def __init__(self, responses: list):
        self.responses = copy.deepcopy(responses)
        self.calls = []

    async def propose(self, dispatch_input, *, feedback, previous_response, audit_dir):
        index = len(self.calls)
        self.calls.append(copy.deepcopy({'dispatch_input': dispatch_input, 'feedback': feedback,
                                        'previous_response': previous_response}))
        result = copy.deepcopy(self.responses[min(index, len(self.responses) - 1)])
        if isinstance(result, Exception):
            raise result
        if 'schedule' in result:
            return result
        return {'schedule': result, 'raw_response': json.dumps(result), 'metadata': {'model_called': False}}


class LLMSchedulingProvider:
    def __init__(self):
        from core301.dispatch.providers import LLMDispatchProvider
        self.provider = LLMDispatchProvider()

    async def propose(self, dispatch_input, *, feedback, previous_response, audit_dir):
        prompt = (PROJECT_ROOT / 'src/core301/dispatch/prompts/resource_schedule.md').read_bytes()
        meta = {'requested_model': self.provider._config.model, 'prompt_sha256': sha256(prompt),
                'returned_model': None, 'usage': None, 'max_retries': 0, 'timeout_s': 180}
        write_json(audit_dir / 'llm_request_metadata.json', meta)
        try:
            result = await self.provider.decide_resource_schedule(
                dispatch_input, feedback=feedback, previous_response=previous_response,
                timeout_s=180, audit_dir=audit_dir)
            result['metadata'] = {**meta, **result['metadata']}
            write_json(audit_dir / 'response_metadata.json', result['metadata'])
            return result
        except Exception as exc:
            write_json(audit_dir / 'llm_error.json', {**safe_error(exc), 'retry_attempted': False})
            raise
