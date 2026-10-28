"""Sanitized per-patient decisions, strict admission and host-owned plan expansion."""
import copy
import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core301.dispatch.minimal import api
from core301.paths import PROJECT_ROOT
from core301.pulse.observation_projector import REQUESTS
from .audit import safe_error, sha256, write_json

PROMPT_PATH = Path(__file__).with_name('prompts') / 'treatment_candidates_v1.md'
INJURY_CONFIG = PROJECT_ROOT / 'research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json'
DEFAULT_MAX_TOKENS = 8192


def validate_max_tokens(value: int) -> int:
    if type(value) is not int or not 256 <= value <= 32768:
        raise ValueError('treatment_max_tokens must be between 256 and 32768')
    return value


class TreatmentFailure(RuntimeError):
    """A classified provider failure containing only safe audit information."""
    def __init__(self, reason_code: str, **details):
        self.reason = {'reason_code': reason_code, **details}
        super().__init__(reason_code)


class InvalidJSON(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class Candidate(StrictModel):
    actions: list[str] = Field(min_length=1)
    rationale: str

    @model_validator(mode='after')
    def unique_actions(self):
        if len(self.actions) != len(set(self.actions)):
            raise ValueError('Repeated action')
        return self


class TreatmentDecision(StrictModel):
    schema_version: Literal['301.treatment.candidates.v1']
    patient_id: str
    decision_type: Literal['propose_candidates', 'no_treatment_needed']
    candidate_plans: list[Candidate] = Field(max_length=2)
    reasoning_summary: str
    refusal_reason: str | None

    @model_validator(mode='after')
    def decision_shape(self):
        if self.decision_type == 'propose_candidates':
            if not self.candidate_plans:
                raise ValueError('Candidates required')
        elif self.candidate_plans or not self.refusal_reason or not self.refusal_reason.strip():
            raise ValueError('No treatment requires empty candidates and a reason')
        sequences = [tuple(p.actions) for p in self.candidate_plans]
        if len(sequences) != len(set(sequences)):
            raise ValueError('Identical candidate sequences')
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise InvalidJSON('Nonfinite JSON constant: ' + value)


def decode(raw: str) -> TreatmentDecision:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except json.JSONDecodeError as exc:
        raise InvalidJSON(str(exc)) from exc
    return TreatmentDecision.model_validate(value)


def build_treatment_input(case: dict, mapping: dict) -> dict:
    profiles = api.read(INJURY_CONFIG)['profiles']
    injury = {key: case['known_injury_context'][key]
              for key in ('injury_type', 'side', 'compartment')
              if key in case['known_injury_context']}
    allowed = next(p['actions'] for p in profiles if p['injury_type'] == injury['injury_type'])
    # Allowlist the five measurements even if a future caller has extra grants.
    obs = case['observation']
    vitals = {}
    for field, (_, _, unit, _, _) in REQUESTS.items():
        if field.startswith('vitals.'):
            name = field.split('.')[1]
            vitals[name] = {key: copy.deepcopy(obs['vitals'][name][key])
                            for key in ('value', 'status', 'observed_at_s')}
            vitals[name]['unit'] = unit or 'fraction'
    return {
        'patient_id': case['patient_id'], 'location': case['location'],
        'arrival_time_min': case['arrival_time_min'], 'known_injury_context': injury,
        'observation': {'patient_id': case['patient_id'], 'simulation_time_s': obs['simulation_time_s'],
                        'vitals': vitals},
        'allowed_actions': list(allowed),
        'action_descriptions': {
            kind: {key: copy.deepcopy(mapping['actions'][kind].get(key, {} if key == 'injury_predecessors' else []))
                   for key in ('allowed_start', 'predecessor_actions', 'injury_predecessors')}
            for kind in allowed
        },
    }


def admit(raw: str, payload: dict, mapping: dict, *, plan_status: str,
          dataset_dir: Path = api.DATASET) -> tuple[dict, list]:
    decision = decode(raw)
    if decision.patient_id != payload['patient_id']:
        raise ValueError('Patient identity mismatch')
    injury = payload['known_injury_context']
    for plan in decision.candidate_plans:
        previous = set()
        for kind in plan.actions:
            if kind not in payload['allowed_actions']:
                raise ValueError('Action not allowed: ' + kind)
            rule = mapping['actions'][kind]
            required = list(rule.get('predecessor_actions', []))
            predecessor = rule.get('injury_predecessors', {}).get(injury['injury_type'])
            if predecessor:
                required.append(predecessor)
            if not set(required) <= previous:
                raise ValueError('Predecessor missing or out of order: ' + kind)
            previous.add(kind)
    references, protocols = {}, {}
    for plan in api.read(Path(dataset_dir) / 'action_plan_templates.json'):
        for action in plan['actions']:
            kind, ref = action['action_type'], action['resource_mapping_ref']
            if kind in references and references[kind] != ref:
                raise ValueError('Inconsistent template resource reference: ' + kind)
            references[kind] = ref
            key = (plan['injury_type'], kind)
            protocol = action['fixed_protocol_ref']
            if key in protocols and protocols[key] != protocol:
                raise ValueError('Inconsistent template protocol reference: ' + str(key))
            protocols[key] = protocol
    plans = []
    sequences = [p.actions for p in decision.candidate_plans] or [[]]
    for n, sequence in enumerate(sequences, 1):
        plan_id = f'{decision.patient_id}-plan-{n}'
        actions = []
        for i, kind in enumerate(sequence, 1):
            target = {'patient_id': decision.patient_id}
            target_kind = mapping['actions'][kind]['target_kind']
            if target_kind in ('side', 'compartment'):
                target[target_kind] = injury[target_kind]
            actions.append({
                'action_id': f'{plan_id}-a{i}', 'action_type': kind, 'target': target,
                'depends_on': [f'{plan_id}-a{i-1}'] if i > 1 else [],
                # User clarification: preserve the entire injury/action-specific
                # template reference, including restricted-profile selectors.
                'fixed_protocol_ref': copy.deepcopy(protocols[(injury['injury_type'], kind)]),
                'resource_mapping_ref': copy.deepcopy(references[kind]),
                'eligibility_status': 'eligibility_pending',
                'injury_association': copy.deepcopy(injury),
            })
        plans.append({'plan_id': plan_id, 'injury_type': injury['injury_type'],
                      'status': plan_status, 'actions': actions})
    return decision.model_dump(), plans


def template_decisions(dataset_dir: Path = api.DATASET) -> dict[str, str]:
    dataset_dir = Path(dataset_dir)
    templates = {p['plan_id']: p for p in api.read(dataset_dir / 'action_plan_templates.json')}
    result = {}
    for patient in api.read(dataset_dir / 'patients_initial.json'):
        plans = [templates[p] for p in patient['plan_ids']]
        sequences = [[a['action_type'] for a in p['actions']] for p in plans]
        empty = sequences == [[]]
        result[patient['patient_id']] = json.dumps({
            'schema_version': '301.treatment.candidates.v1', 'patient_id': patient['patient_id'],
            'decision_type': 'no_treatment_needed' if empty else 'propose_candidates',
            'candidate_plans': [] if empty else [{'actions': seq, 'rationale': 'Dataset template'} for seq in sequences],
            'reasoning_summary': 'Fixed dataset baseline; no model called',
            'refusal_reason': 'Dataset template has no treatment actions' if empty else None,
        }, allow_nan=False)
    return result


class TreatmentProvider(Protocol):
    plan_status: str

    async def propose(self, payload: dict, *, audit_dir: Path) -> str: ...


class FakeTreatmentProvider:
    plan_status = 'template_only_not_executed'

    def __init__(self, responses: dict[str, str | dict | Exception], *, finish_reasons: dict | None = None):
        self.responses = copy.deepcopy(responses)
        self.finish_reasons = dict(finish_reasons or {})

    async def propose(self, payload: dict, *, audit_dir: Path) -> str:
        response = self.responses[payload['patient_id']]
        if isinstance(response, Exception):
            raise response
        raw = response if isinstance(response, str) else json.dumps(response, allow_nan=False)
        if payload['patient_id'] in self.finish_reasons:
            finish_reason = self.finish_reasons[payload['patient_id']]
            write_json(audit_dir / 'response_metadata.json', {'model_called': False, 'finish_reason': finish_reason})
            (audit_dir / 'response.txt').write_text(raw)
            if finish_reason == 'length':
                raise TreatmentFailure('OUTPUT_TRUNCATED', finish_reason=finish_reason)
        return raw


class TemplateTreatmentProvider(FakeTreatmentProvider):
    def __init__(self, dataset_dir: Path = api.DATASET):
        super().__init__(template_decisions(dataset_dir))


class LLMTreatmentProvider:
    plan_status = 'agent_proposed_not_executed'

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        from core301.agent.llm_config import load_llm_config
        self.max_tokens = validate_max_tokens(max_tokens)
        self.config = load_llm_config(PROJECT_ROOT)
        self.called: set[str] = set()

    async def propose(self, payload: dict, *, audit_dir: Path) -> str:
        from openai import AsyncOpenAI
        pid = payload['patient_id']
        if pid in self.called:
            raise RuntimeError('One request per patient; no retry or fallback')
        self.called.add(pid)
        prompt = PROMPT_PATH.read_text()
        request = {'model': self.config.model, 'max_tokens': self.max_tokens, 'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, allow_nan=False)},
        ]}
        metadata = {'requested_model': self.config.model, 'returned_model': None, 'usage': None,
                    'prompt_sha256': sha256(prompt.encode()), 'max_retries': 0, 'timeout_s': 60}
        write_json(audit_dir / 'llm_request.json', {**metadata, 'parameters': request})
        try:
            async with AsyncOpenAI(api_key=self.config.api_key, base_url=self.config.base_url,
                                   max_retries=0, timeout=60) as client:
                response = await client.chat.completions.create(**request)
            write_json(audit_dir / 'llm_response.json', response.model_dump(mode='json'))
            content = response.choices[0].message.content if response.choices else None
            raw = content if isinstance(content, str) else ''
            (audit_dir / 'response.txt').write_text(raw)
            metadata.update(returned_model=response.model,
                            usage=response.usage.model_dump() if response.usage is not None else None,
                            finish_reason=response.choices[0].finish_reason if response.choices else None)
            if metadata['finish_reason'] == 'length':
                raise TreatmentFailure('OUTPUT_TRUNCATED', finish_reason='length')
            if not raw.strip():
                raise TreatmentFailure('EMPTY_RESPONSE', finish_reason=metadata['finish_reason'])
            return raw
        except TreatmentFailure as exc:
            write_json(audit_dir / 'llm_error.json', {**exc.reason, 'retry_attempted': False})
            raise
        except Exception as exc:
            write_json(audit_dir / 'llm_error.json', {**safe_error(exc), 'retry_attempted': False})
            raise TreatmentFailure('CALL_FAILED', **safe_error(exc)) from None
        finally:
            write_json(audit_dir / 'response_metadata.json', metadata)
