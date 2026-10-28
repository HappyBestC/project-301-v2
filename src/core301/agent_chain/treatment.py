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
    raise ValueError('Nonfinite JSON constant: ' + value)


def decode(raw: str) -> TreatmentDecision:
    return TreatmentDecision.model_validate(json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant))


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
            vitals[name] = {**copy.deepcopy(obs['vitals'][name]), 'unit': unit or 'fraction'}
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


def admit(raw: str, payload: dict, mapping: dict, *, plan_status: str) -> tuple[dict, list]:
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
    references = {}
    for plan in api.read(api.DATASET / 'action_plan_templates.json'):
        for action in plan['actions']:
            kind, ref = action['action_type'], action['resource_mapping_ref']
            if kind in references and references[kind] != ref:
                raise ValueError('Inconsistent template resource reference: ' + kind)
            references[kind] = ref
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
                'fixed_protocol_ref': {'protocol_id': f'{kind}.phase1.1',
                                       'source': 'src/core301/pulse/v2/protocol_book.py'},
                'resource_mapping_ref': copy.deepcopy(references[kind]),
                'eligibility_status': 'eligibility_pending',
                'injury_association': copy.deepcopy(injury),
            })
        plans.append({'plan_id': plan_id, 'injury_type': injury['injury_type'],
                      'status': plan_status, 'actions': actions})
    return decision.model_dump(), plans


def template_decisions() -> dict[str, str]:
    templates = {p['plan_id']: p for p in api.read(api.DATASET / 'action_plan_templates.json')}
    result = {}
    for patient in api.read(api.DATASET / 'patients_initial.json'):
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

    def __init__(self, responses: dict[str, str | dict | Exception]):
        self.responses = copy.deepcopy(responses)

    async def propose(self, payload: dict, *, audit_dir: Path) -> str:
        response = self.responses[payload['patient_id']]
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response, allow_nan=False)


class TemplateTreatmentProvider(FakeTreatmentProvider):
    def __init__(self):
        super().__init__(template_decisions())


class LLMTreatmentProvider:
    plan_status = 'agent_proposed_not_executed'

    def __init__(self):
        from core301.agent.llm_config import load_llm_config
        self.config = load_llm_config(PROJECT_ROOT)
        self.called: set[str] = set()

    async def propose(self, payload: dict, *, audit_dir: Path) -> str:
        from openai import AsyncOpenAI
        pid = payload['patient_id']
        if pid in self.called:
            raise RuntimeError('One request per patient; no retry or fallback')
        self.called.add(pid)
        prompt = PROMPT_PATH.read_text()
        request = {'model': self.config.model, 'max_tokens': 1200, 'messages': [
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
            if not raw.strip():
                raise ValueError('Empty response')
            return raw
        except Exception as exc:
            write_json(audit_dir / 'llm_error.json', {**safe_error(exc), 'retry_attempted': False})
            raise RuntimeError('LLM_CALL_FAILED:' + type(exc).__name__) from None
        finally:
            write_json(audit_dir / 'response_metadata.json', metadata)
