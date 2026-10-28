"""M3-A draft and host admission. No V1 plan conversion or native parameters."""
import json
from typing import Literal
from pydantic import Field, model_validator
from core301.contracts.base import Contract
from core301.contracts.observation import PatientObservation
from core301.dispatch.complete_contracts import CompletePlan, CompleteAction
from core301.pulse.observation_projector import BASIC, REQUESTS


class DraftAction(Contract):
    action_type: Literal['control_external_bleeding']
    compartment: Literal['RightLeg']


class TreatmentDecisionDraft(Contract):
    schema_version: Literal['301.treatment.decision.m3a.1']
    decision_type: Literal['propose_plan', 'defer', 'insufficient_evidence']
    actions: list[DraftAction]
    reasoning_summary: str = Field(min_length=1, max_length=2000)
    refusal_reason: str | None

    @model_validator(mode='after')
    def decision_semantics(self):
        if self.decision_type == 'propose_plan':
            if len(self.actions) != 1 or self.refusal_reason is not None:
                raise ValueError('Exactly one admitted action required; no duplicate or additional sequence')
        elif self.actions or not self.refusal_reason or not self.refusal_reason.strip():
            raise ValueError('Refusal/defer requires reason and no actions')
        return self


def parse_decision(content):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: '+key)
            result[key] = value
        return result
    return TreatmentDecisionDraft.model_validate(json.loads(content, object_pairs_hook=unique))


def agent_input(observation, patient_id, known_injuries):
    """Explicit M3-A grant: five basic measurements and registry-authorized injury.

    Conditional tests and evaluation diagnostics are intentionally not granted.
    Units originate from the established request map; absent values stay absent.
    """
    obs = PatientObservation.model_validate(observation)
    if obs.patient_id != patient_id or abs(obs.simulation_time_s-180) > 1e-6:
        raise ValueError('Patient/time mismatch at the fixed decision point')
    expected = [{'injury_type':'external_hemorrhage', 'compartment':'RightLeg'}]
    if known_injuries != expected:
        raise ValueError('Authorized clinical context differs from admitted scenario')
    measures = {}
    for path in BASIC:
        group, field = path.split('.')
        measure = getattr(getattr(obs, group), field)
        if measure.observed_at_s is not None and measure.observed_at_s > obs.simulation_time_s:
            raise ValueError('Future measurement')
        measures[path] = {**measure.model_dump(), 'unit': REQUESTS[path][2] or '1'}
    return dict(schema_version='301.treatment.input.m3a.1', patient_id=patient_id,
                simulation_time_s=obs.simulation_time_s, known_injuries=expected,
                measurements=measures, allowed_actions=['control_external_bleeding'])


def build_complete_plan(draft, run_id, patient_id):
    draft = TreatmentDecisionDraft.model_validate(draft)
    if draft.decision_type != 'propose_plan':
        raise ValueError('MODEL_'+draft.decision_type.upper())
    # Every action/target below is copied from the validated model draft.
    actions = tuple(CompleteAction(action_instance_id=f'{run_id}-action-{i+1}',
                    **action.model_dump(), depends_on=() if i==0 else (f'{run_id}-action-{i}',))
                    for i, action in enumerate(draft.actions))
    return CompletePlan(schema_version='301.treatment.complete.1', run_id=run_id,
        patient_id=patient_id, plan_id=run_id+'-plan', scope_kind='research_fixture',
        scope_id='external_hemorrhage', severity=.4, location_id='scene',
        execution_policy='m2a_serial_execution', parameter_policy='fixed_profile_no_overrides', actions=actions)
