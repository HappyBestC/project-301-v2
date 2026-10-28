"""M3-C1 ordering only; no executable parameters or inventory mutation authority."""
import json
from typing import Literal, Protocol
from pydantic import Field, model_validator
from core301.contracts.base import Contract, Time
from core301.agent.complete_decision import agent_input
from core301.dispatch.complete_contracts import catalog

VERSION = '301.resource.priority.m3c1.1'

class MultiPatientPriorityInput(Contract):
    schema_version: Literal['301.resource.priority.input.m3c1.1']
    run_id: str
    simulation_time_s: Time
    patients: list[dict]
    resource_snapshot: dict
    resource_state_version: int
    allowed_scope: Literal['order_pending_patients_only']

class MultiPatientPriorityDecision(Contract):
    schema_version: Literal['301.resource.priority.m3c1.1']
    run_id: str
    simulation_time_s: Time
    resource_state_version: int
    decision_type: Literal['prioritize', 'defer', 'refuse']
    ordered_patient_ids: list[str]
    reasoning_summary: str = Field(min_length=1, max_length=2000)
    refusal_reason: str | None

    @model_validator(mode='after')
    def semantics(self):
        if self.decision_type == 'prioritize':
            if not self.ordered_patient_ids or self.refusal_reason is not None:
                raise ValueError('Invalid prioritize decision')
        elif self.ordered_patient_ids or not self.refusal_reason or not self.refusal_reason.strip():
            raise ValueError('Refusal requires empty order and reason')
        return self

class PriorityDecisionProvider(Protocol):
    def create_decision(self, payload: dict, directory) -> str: ...

def build_input(host):
    patients=[]
    for p in host.patients.values():
        if p.state != 'PLAN_READY':
            raise ValueError('Patient not pending')
        item=agent_input(p.runtime.observe(), p.plan.patient_id, p.runtime.registry.known())
        item.pop('schema_version');item.pop('allowed_actions')
        item['plan_summary']=[{'action_type':a.action_type,'compartment':a.compartment,
            'required_resources':dict(catalog().requirements[a.action_type].holds + catalog().requirements[a.action_type].stock)} for a in p.plan.actions]
        patients.append(item)
    snapshot=host.manager.get_snapshot(host.run_id)
    return MultiPatientPriorityInput(schema_version='301.resource.priority.input.m3c1.1',run_id=host.run_id,
        simulation_time_s=host.global_simulation_time_s,patients=patients,resource_snapshot=snapshot,
        resource_state_version=snapshot['state_version'],allowed_scope='order_pending_patients_only').model_dump(mode='json')

def parse_decision(content):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    return MultiPatientPriorityDecision.model_validate(json.loads(content,object_pairs_hook=unique))

def validate_decision(decision,payload,*,current_time,current_version):
    d=MultiPatientPriorityDecision.model_validate(decision)
    if d.run_id!=payload['run_id']:raise ValueError('RUN_MISMATCH')
    if d.simulation_time_s!=payload['simulation_time_s'] or current_time!=d.simulation_time_s:raise ValueError('DECISION_TIME_MISMATCH')
    if d.resource_state_version!=payload['resource_state_version'] or current_version!=d.resource_state_version:raise ValueError('STALE_SNAPSHOT')
    if d.decision_type!='prioritize':raise ValueError('MODEL_'+d.decision_type.upper())
    expected=[p['patient_id'] for p in payload['patients']]
    if len(d.ordered_patient_ids)!=len(expected) or set(d.ordered_patient_ids)!=set(expected):raise ValueError('PATIENT_PERMUTATION_REQUIRED')
    return d

class FixedPriorityProvider:
    def __init__(self,mode):
        if mode not in ('fixed_A_first','fixed_B_first'):raise ValueError('Unknown fixed priority')
        self.mode=mode
    def create_decision(self,payload,directory):
        ids=[p['patient_id'] for p in payload['patients']]
        ids.sort(key=lambda x: x.rsplit('-',1)[-1],reverse=self.mode=='fixed_B_first')
        return json.dumps(dict(schema_version=VERSION,run_id=payload['run_id'],simulation_time_s=payload['simulation_time_s'],
            resource_state_version=payload['resource_state_version'],decision_type='prioritize',ordered_patient_ids=ids,
            reasoning_summary='Engineering baseline: '+self.mode,refusal_reason=None))
