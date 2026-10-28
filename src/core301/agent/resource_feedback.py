"""Authorized resource feedback and strict control decisions, never treatment plans."""
import json
from typing import Literal
from pydantic import Field
from core301.contracts.base import Contract, Time
from core301.contracts.observation import PatientObservation
from core301.pulse.observation_projector import BASIC, REQUESTS
from core301.dispatch.shared_resources.models import Result

DecisionType=Literal['KEEP_PLAN_AND_WAIT','RECHECK_RESOURCES','DEFER_INSUFFICIENT_EVIDENCE','STOP_UNEXECUTABLE']
VERSION='301.treatment.feedback.m3c2.1'

class ResourceFeedback(Contract):
    schema_version: Literal['301.resource.feedback.m3c2.1']
    run_id: str
    patient_id: str
    plan_id: str
    decision_id: str
    global_simulation_time_s: Time
    plan_state: str
    pending_actions: list[dict]
    m2_result: dict
    conflict_codes: list[str]
    resource_ids: list[str]
    blocking_allocation_ids: list[str]
    resource_state_version: int
    resource_changed: bool
    trigger_event_sequence: int | None
    next_check_condition: str
    timing_protocol: dict
    allowed_operations: list[DecisionType]
    unresolved_execution: bool

class TreatmentFeedbackDecision(Contract):
    schema_version: Literal['301.treatment.feedback.m3c2.1']
    run_id: str
    patient_id: str
    plan_id: str
    decision_id: str
    global_simulation_time_s: Time
    resource_state_version: int
    decision_type: DecisionType
    reasoning_summary: str=Field(min_length=1,max_length=2000)
    refusal_reason: str | None

def parse_decision(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Duplicate JSON key')
            result[k]=v
        return result
    return TreatmentFeedbackDecision.model_validate(json.loads(raw,object_pairs_hook=unique))

def validate_decision(d,feedback,*,current_version,current_time):
    d=TreatmentFeedbackDecision.model_validate(d);f=ResourceFeedback.model_validate(feedback)
    for name in ('run_id','patient_id','plan_id','decision_id','global_simulation_time_s','resource_state_version'):
        if getattr(d,name)!=getattr(f,name):raise ValueError('FEEDBACK_CONTEXT_MISMATCH:'+name)
    if current_version!=f.resource_state_version:raise ValueError('STALE_SNAPSHOT')
    if current_time!=f.global_simulation_time_s:raise ValueError('DECISION_TIME_MISMATCH')
    if d.decision_type not in f.allowed_operations:raise ValueError('OPERATION_NOT_ALLOWED')
    if d.decision_type=='DEFER_INSUFFICIENT_EVIDENCE' and not d.refusal_reason:raise ValueError('Defer requires reason')
    if d.decision_type in ('KEEP_PLAN_AND_WAIT','RECHECK_RESOURCES') and d.refusal_reason is not None:raise ValueError('Conflicting refusal')
    return d

def authorized_observation(observation,patient_id,current_time):
    obs=PatientObservation.model_validate(observation)
    if obs.patient_id!=patient_id or abs(obs.simulation_time_s-current_time)>1e-6:raise ValueError('Observation identity/time mismatch')
    measures={}
    for path in BASIC:
        group,field=path.split('.');m=getattr(getattr(obs,group),field)
        if m.observed_at_s is not None and m.observed_at_s>obs.simulation_time_s:raise ValueError('Future sample')
        measures[path]={**m.model_dump(),'unit':REQUESTS[path][2] or '1'}
    return {'patient_id':patient_id,'simulation_time_s':obs.simulation_time_s,'measurements':measures}

def build_feedback(host,label,result,*,decision_id,trigger=None):
    p=host.patients[label];r=Result.model_validate(result.resource_result)
    if (r.run_id,r.patient_id,r.plan_id)!=(host.run_id,p.plan.patient_id,p.plan.plan_id):raise ValueError('Cross-patient backend result')
    snapshot=host.manager.get_snapshot(host.run_id)
    codes=[c.code for c in r.conflicts]
    unresolved=p.request_id is not None or 'EXECUTION_UNCERTAIN' in codes or any(
        a['patient_id']==p.plan.patient_id and a['status'] in ('IN_USE','QUARANTINED') for a in snapshot['allocations'].values())
    changed=snapshot['state_version']!=r.state_version
    if trigger is not None:
        event=host.events[trigger-1]
        if event['kind']!='RESOURCE_RELEASED' or event['state_version']!=snapshot['state_version']:raise ValueError('Unproven wake event')
    allowed=['DEFER_INSUFFICIENT_EVIDENCE','STOP_UNEXECUTABLE']
    if not unresolved:
        if trigger is not None and changed:allowed.insert(0,'RECHECK_RESOURCES')
        elif set(codes)&{'RESOURCE_IN_USE','RESOURCE_SHORTAGE'}:allowed.insert(0,'KEEP_PLAN_AND_WAIT')
        elif 'STALE_SNAPSHOT' in codes:allowed.insert(0,'RECHECK_RESOURCES')
    actions=[{'action_type':a.action_type,'compartment':a.compartment} for a in p.plan.actions]
    feedback=ResourceFeedback(schema_version='301.resource.feedback.m3c2.1',run_id=host.run_id,patient_id=p.plan.patient_id,
        plan_id=p.plan.plan_id,decision_id=decision_id,global_simulation_time_s=host.global_simulation_time_s,
        plan_state=p.state,pending_actions=actions if not p.request_id else [],m2_result=r.model_dump(mode='json'),
        conflict_codes=codes,resource_ids=list(dict.fromkeys(c.resource_id for c in r.conflicts if c.resource_id)),
        blocking_allocation_ids=list(dict.fromkeys(a for c in r.conflicts for a in c.blocking_allocation_ids)),
        resource_state_version=snapshot['state_version'],resource_changed=changed,trigger_event_sequence=trigger,
        next_check_condition='actual RESOURCE_RELEASED event with changed ledger version; no predicted release time',
        timing_protocol={'protocol_version':host.timing['protocol_version'],'execution_allowed_now':host.treatment_time_allowed(),
                         'candidate_treatment_times_s':host.timing['candidate_treatment_times_s']},
        allowed_operations=allowed,unresolved_execution=unresolved)
    known=p.runtime.registry.known()
    if known!=[{'injury_type':'external_hemorrhage','compartment':'RightLeg'}]:raise ValueError('Unauthorized injury scope')
    payload={'feedback':feedback.model_dump(mode='json'),'observation':authorized_observation(p.runtime.observe(),p.plan.patient_id,host.global_simulation_time_s),
        'known_injuries':known,'plan_summary':actions,'resource_snapshot':snapshot,
        'waiting_state':p.state,'executed_actions':[] if not p.request_id else [{'request_id':p.request_id,'status':p.state}],
        'allowed_scope':'control pending task only; no revised plan or native parameters'}
    return feedback,payload

class FixedFeedbackProvider:
    """Explicit engineering baseline. Never counted as a real model."""
    def __init__(self,decisions=('KEEP_PLAN_AND_WAIT','RECHECK_RESOURCES')):self.decisions=iter(decisions)
    def create_decision(self,payload,directory):
        f=payload['feedback'];kind=next(self.decisions)
        return json.dumps({**{k:f[k] for k in ('run_id','patient_id','plan_id','decision_id','global_simulation_time_s','resource_state_version')},
            'schema_version':VERSION,'decision_type':kind,'reasoning_summary':'Explicit fixed offline/exploratory baseline',
            'refusal_reason':'Insufficient evidence' if kind=='DEFER_INSUFFICIENT_EVIDENCE' else None})
