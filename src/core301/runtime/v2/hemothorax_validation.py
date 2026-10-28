"""Engineering validation only. No efficacy rule or research admission is granted.

The existing CaseRuntime/ProtocolBook remain closed to hemothorax. This explicit
validation route records raw execution and leaves its goal decision pending.
"""
import hashlib,json,math,copy
from uuid import uuid4
from pydantic import ValidationError
from core301.contracts.v2.injury import CasualtyInput
from core301.contracts.v2.treatment import TreatmentPlan
from core301.contracts.v2.hemothorax_observation import HemothoraxCaseContext
from core301.contracts.context import ResourceState
from core301.pulse.observation_projector import BASIC
from core301.pulse.v2.hemothorax_session import HemothoraxSession
from core301.pulse.v2.injury_adapter import InjuryAdapter
from core301.pulse.injury_adapter import scalar
from core301.pulse.v2.session import native_scalar
from core301.pulse.v2.hemothorax_numeric_review import review_overshoot
from .case_runtime import CaseRuntime, DecisionContext
from .errors import V2Error
from .hemothorax_resources import HemothoraxResources, COSTS

PROFILE='301.v2.hemothorax.engineering_validation.1'
MONITORS=(*BASIC,'respiratory.tidal_volume','laboratory.arterial_oxygen_pressure','laboratory.arterial_carbon_dioxide_pressure',
          'laboratory.blood_ph','circulation.cardiac_output','laboratory.hemoglobin_concentration')

class HemothoraxValidationRuntime(CaseRuntime):
    def __init__(self,*args,validation_only=False,drainage_access=False,**kwargs):
        if validation_only is not True:raise V2Error('RESEARCH_RULE_APPROVAL_PENDING','Explicit engineering validation is required; clinical admission is not approved')
        if kwargs.get('mode','production')!='research':raise V2Error('PRODUCTION_NOT_ENABLED','Hemothorax is not production enabled')
        if 'session' in kwargs:raise V2Error('NATIVE_SESSION_REQUIRED','This validation route owns a real Pulse session')
        super().__init__(*args,**kwargs)
        self.session=HemothoraxSession(self.patient_id,(*BASIC,*sorted(self.access.visible())))
        self.drainage_access=drainage_access is True
        self._tube_seen=False;self._submitted_kinds=set();self._baseline_volume=None;self._stopped_volume=None
        self.journal.data.setdefault('hemothorax_validation',{'profile':PROFILE,'admission':'PENDING_RESEARCH_RULE_APPROVAL','goal_passed':False})
        self.journal.flush()

    def _deny(self,code,message,request_id=None):
        now=self.session.get_simulation_time() if self.session.ready else None
        self.journal.event(request_id,None,'REJECTED',now,error={'code':code,'message':message})
        raise V2Error(code,message)

    def prepare(self,casualty):
        with self._lock:
            if self.journal.reopened:self._deny('RESTART_REQUIRES_RECOVERY','Restart is query-only; native state is not restored')
            if self._prepared or self._closed:self._deny('ALREADY_PREPARED','Use a new continuous session')
            try:casualty=CasualtyInput.model_validate(casualty)
            except ValidationError as exc:self._deny('INVALID_INJURY_SCHEMA',str(exc))
            if casualty.patient_id!=self.patient_id:self._deny('PATIENT_MISMATCH','Wrong patient')
            if len(casualty.injuries)!=1:self._deny('UNVALIDATED_SCOPE','Exactly one source')
            i=casualty.injuries[0]
            if i.injury_type!='hemothorax' or i.severity!=.8 or i.side!='Left':self._deny('UNVALIDATED_SCOPE','Only Left .8 hemothorax is verified')
            self.casualty=casualty
            self._write('initialization.json',{'profile':PROFILE,'healthy_s':60,'injury_s':600,'decision_s':660,'end_s':960,'casualty':casualty.model_dump()})
            try:
                self.session.initialize(self.directory/'pulse.log');self.session.advance_time(60)
                self.session._submit(InjuryAdapter().convert_dynamic(i),'injury');self.session.advance_time(600)
                self.registry.register(casualty);self._prepared=True
                self._baseline_volume=self.session.drainage(self.session_epoch).residual_blood_volume_mL.value
            except Exception as exc:
                self._halted=True;self._deny('INITIALIZATION_FAILED',str(exc))
            return self.observe()

    def drainage_observation(self):
        if not self.drainage_access:self._deny('DRAINAGE_ACCESS_DENIED','No explicit read-only drainage observation grant')
        if not self._prepared or self._closed:self._deny('NOT_PREPARED','No live observation session')
        return self.session.drainage(self.session_epoch)

    def build_context(self,*,authorized_locations=None):
        with self._lock:
            if not self._prepared or self._closed:self._deny('NOT_PREPARED','No live case')
            known=self.registry.known()
            if authorized_locations is not None:known=[i for i in known if i['side'] in authorized_locations]
            resource=self.resources.snapshot(self.run_id,self.patient_id) if self.resources else ResourceState(**{k:0 for k in ResourceState.model_fields})
            public=HemothoraxCaseContext(patient_id=self.patient_id,known_injuries=known,patient_observation=self.observe(),available_resources=resource,
                drainage_observation=self.drainage_observation() if self.drainage_access else None)
            ref=uuid4().hex;self._contexts[ref]=(public.model_dump(),self.registry.signature())
            return DecisionContext(ref,HemothoraxCaseContext.model_validate(public.model_dump()))

    def _check_source(self):
        if len(self.registry.sources())!=1:raise V2Error('UNVALIDATED_MULTISOURCE','Single source required')
        s,=self.registry.sources()
        if not s.active or not s.authorized or s.patient_id!=self.patient_id or s.injury_type!='hemothorax' or s.side!='Left' or s.initial_severity!=.8:
            raise V2Error('TARGET_NOT_AUTHORIZED','Wrong/revoked registry source')
        state=self.session.execution_state();super()._validate_native_sources(state,s)
        if not s.controlled:
            h=state['actions']['Hemothorax'][0]
            if native_scalar(h,'Severity')!=.8:raise V2Error('STALE_NATIVE_SOURCE','Native severity differs from the trusted source')
        return s,state

    def execute_plan(self,plan,*,request_id,context_ref):
        with self._lock:
            if not isinstance(request_id,str) or not request_id.strip():self._deny('INVALID_REQUEST_ID','Nonempty request ID required')
            try:plan=TreatmentPlan.model_validate(plan)
            except ValidationError as exc:self._deny('INVALID_TREATMENT_SCHEMA',str(exc),request_id)
            digest=hashlib.sha256(json.dumps(plan.model_dump(),sort_keys=True).encode()).hexdigest()
            old=self.query(request_id)
            if old:
                if old['plan_sha256']!=digest or old['context_ref']!=context_ref:self._deny('IDEMPOTENCY_CONFLICT','Changed request payload/context',request_id)
                return old
            if self.journal.reopened:self._deny('RESTART_REQUIRES_RECOVERY','Only query permitted',request_id)
            if not self._prepared or self._closed:self._deny('NOT_PREPARED','No live case',request_id)
            if self._halted:self._deny('EXECUTION_HALTED','Prior uncertainty blocks execution',request_id)
            now=self.session.get_simulation_time();pid=uuid4().hex
            rec={'plan_id':pid,'request_id':request_id,'plan_sha256':digest,'context_ref':context_ref,'plan':plan.model_dump(),'status':'PROPOSED',
                 'production_enabled':False,'profile':PROFILE,'admission':'PENDING_RESEARCH_RULE_APPROVAL','goal_passed':False,'actions':[],'error':None}
            self.journal.data['plans'][request_id]=rec;self.journal.event(request_id,None,'PROPOSED',now)
            try:
                if context_ref not in self._contexts:raise V2Error('CONTEXT_NOT_FOUND','Context belongs to another case/session')
                public_data,signature=self._contexts[context_ref];public=HemothoraxCaseContext.model_validate(public_data)
                if plan.patient_id!=self.patient_id:raise V2Error('PATIENT_MISMATCH','Wrong plan patient')
                if signature!=self.registry.signature():raise V2Error('STALE_SOURCE','Registry changed since context')
                source,state=self._check_source()
                if self._control_only and plan.actions:raise V2Error('CONTROL_BRANCH_ONLY','Control cannot execute actions')
                if plan.actions:
                    if abs(now-660)>1e-6:raise V2Error('UNVALIDATED_TIMING','One plan at 660s only')
                    if source.known() not in [i.model_dump() for i in public.known_injuries]:raise V2Error('TARGET_NOT_AUTHORIZED','Side not disclosed/authorized')
                    if not self.drainage_access or public.drainage_observation is None:raise V2Error('MONITORING_UNAVAILABLE','No authorized drainage observation')
                    if public.drainage_observation.simulation_time_s!=now or public.drainage_observation.residual_blood_volume_mL.status!='available':raise V2Error('MONITORING_UNAVAILABLE','Stale/missing drainage observation')
                    for path in MONITORS:
                        g,f=path.split('.');m=getattr(getattr(public.patient_observation,g,None),f,None)
                        if m is None or m.status!='available' or m.observed_at_s!=now:raise V2Error('MONITORING_UNAVAILABLE','Required public safety data unavailable')
                    if state['airway_mode']!='Free' or state['intubation']!='Off' or state['actions'].get('TubeThoracostomy') or state['actions'].get('SubstanceCompoundInfusion'):
                        raise V2Error('DEVICE_CONFLICT','Existing device/infusion outside fixed profile')
                    if not isinstance(self.resources,HemothoraxResources):raise V2Error('RESOURCE_AUTHORITY_MISSING','Explicit hemothorax validation fixture required')
                for act in plan.actions:
                    if act.action_type not in COSTS:raise V2Error('ACTION_NOT_OPEN','Only source control and tube are under engineering validation')
                    if act.side!=source.side:raise V2Error('TARGET_NOT_AUTHORIZED','Wrong side')
                    if act.action_type in self._submitted_kinds:raise V2Error('ACTION_REPLAY_BLOCKED','No repeated procedure with a new ID')
                if plan.actions:rec['reservation']=self.resources.reserve(pid,plan,self.run_id,self.patient_id)
                for act in plan.actions:
                    if signature!=self.registry.signature():raise V2Error('STALE_SOURCE','Source changed during execution')
                    source,_=self._check_source()
                    item={'action_id':uuid4().hex,'action_type':act.action_type,'target':source.target(),'submitted_time_s':None,'accepted':None,'state':'VALIDATED','lifecycle':'PLANNED'}
                    rec['actions'].append(item)
                    item['resource']=self.resources.begin(pid,item['action_id'],act.action_type)
                    body={'Side':'Left','Severity':scalar('0To1',0)} if act.action_type.startswith('control_') else {'Side':'Left','FlowRate':scalar('VolumePerTime',30,'mL/min')}
                    payload={'PatientAction':{'Hemothorax' if act.action_type.startswith('control_') else 'TubeThoracostomy':body}}
                    item.update(native_payload=payload,submitted_time_s=self.session.get_simulation_time(),state='SUBMITTED',lifecycle='PENDING_NATIVE_RESULT')
                    self._submitted_kinds.add(act.action_type);self.journal.event(request_id,item['action_id'],'SUBMITTED',item['submitted_time_s'])
                    count=len(self.session.action_results)
                    try:
                        result=self.session._submit(payload,'treatment');item.update(accepted=result['accepted'],native_result=result,state='ACCEPTED',lifecycle='PENDING_ADVANCE')
                        self.resources.acknowledge(pid,item['action_id'],True);self.journal.event(request_id,item['action_id'],'ACCEPTED',item['submitted_time_s'])
                    except Exception:
                        result=self.session.action_results[-1] if len(self.session.action_results)>count else None
                        item.update(accepted=result.get('accepted') if result else None,native_result=result,state='UNKNOWN',lifecycle='UNKNOWN')
                        self.resources.acknowledge(pid,item['action_id'],item['accepted']);raise
                    if act.action_type.startswith('control_'):
                        self.session.advance_time(.02)
                        fresh=self.session.drainage(self.session_epoch)
                        if signature!=self.registry.signature() or fresh.source_action_active or fresh.residual_blood_volume_mL.value!=self._baseline_volume:
                            raise V2Error('SOURCE_CONTROL_UNCONFIRMED','Native source control not confirmed; tube not attempted')
                        self.registry.mark_controlled(source.injury_id,source.source_version)
                        item.update(state='COMPLETED',lifecycle='COMPLETED',interpretation='source_control_only_not_blood_restoration')
                    else:
                        self._tube_seen=self.session.drainage(self.session_epoch).tube_action_active
                        item.update(state='ACTIVE' if self._tube_seen else 'UNKNOWN',lifecycle='ACTIVE' if self._tube_seen else 'UNKNOWN')
                        if not self._tube_seen:raise V2Error('TUBE_UNCONFIRMED','Accepted tube not observed active')
                    self.journal.event(request_id,item['action_id'],item['state'],self.session.get_simulation_time())
                rec['status']='EXECUTION_OBSERVED_GOAL_PENDING' if plan.actions else 'VALIDATED_EMPTY_PLAN'
                self.journal.flush()
            except Exception as exc:
                code=exc.code if isinstance(exc,V2Error) else 'NATIVE_EXECUTION_FAILED'
                submitted=any(x['submitted_time_s'] is not None for x in rec['actions'])
                rec.update(status='FAILED_PARTIAL' if submitted else 'REJECTED_BEFORE_EXECUTION',error={'code':code,'message':str(exc)})
                if submitted:
                    self._halted=True
                    for x in rec['actions']:
                        if x['lifecycle']!='COMPLETED':x.update(state='UNKNOWN',lifecycle='UNKNOWN')
                if self.resources:self.resources.release_unused(pid)
                self.journal.event(request_id,None,'FAILED',now,error=rec['error']);raise V2Error(code,str(exc)) from exc
            return self.query(request_id)

    def advance(self,seconds,*,reconcile=True):
        with self._lock:
            if not self._prepared or self._closed or self.journal.reopened:self._deny('NOT_PREPARED','No continuous live session')
            if self._halted:self._deny('EXECUTION_HALTED','Native uncertainty')
            if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:self._deny('INVALID_ADVANCE_ARGUMENT','Finite nonnegative duration required')
            if self.session.get_simulation_time()+seconds>960+1e-6:self._deny('UNVALIDATED_WINDOW','300s after 660s only')
            try:
                self._check_source();self.session.advance_time(seconds);self._check_source()
                d=self.session.drainage(self.session_epoch)
                self._tube_seen |= d.tube_action_active
                if d.residual_blood_volume_mL.status!='available':raise V2Error('DRAINAGE_CONTINUITY_LOST','Native volume unavailable')
                if reconcile:
                    for req,rec in self.journal.data['plans'].items():
                        for item in rec['actions']:
                            if item['action_type']=='chest_tube' and item['accepted'] is True:
                                stops=[e for e in d.events if e.native_time_s>=item['submitted_time_s']]
                                state='ACTIVE' if d.tube_action_active else 'STOPPED' if self._tube_seen and stops else 'UNKNOWN'
                                if item['lifecycle']!=state:self.journal.event(req,item['action_id'],state,d.simulation_time_s)
                                item.update(state=state,lifecycle=state,stop_reason='native_auto_stop_not_efficacy' if state=='STOPPED' else None)
                review=review_overshoot(d.residual_blood_volume_mL.value,dt_s=.02,flow_mL_min=30,source_active=d.source_action_active,tube_active=d.tube_action_active,auto_stop_seen=self._tube_seen and bool(d.events),previous_stopped_volume=self._stopped_volume)
                if not d.tube_action_active and d.events:self._stopped_volume=d.residual_blood_volume_mL.value
                self.journal.data['hemothorax_validation'].update(last_observation=d.model_dump(),numeric_review=review,active_events=self.session.active_events(),goal_passed=False)
                self.journal.flush()
            except Exception as exc:
                self._halted=True;self.journal.event(None,None,'ADVANCE_FAILED',None,error={'type':type(exc).__name__,'message':str(exc)});raise

    def fork_validation(self,directory,*,run_id,resources=None,control_only=False):
        with self._lock:
            if not self._prepared or self._closed or self._halted or self.journal.reopened or self.journal.data['plans'] or abs(self.session.get_simulation_time()-660)>1e-6:
                self._deny('CONTROL_FORK_SCOPE','Only an untouched 660s pretreatment case can fork')
            self._check_source();state=self.session.serialize_state()
            clone=type(self)(self.patient_id,directory,run_id=run_id,mode='research',validation_only=True,drainage_access=self.drainage_access,resources=resources,access=self.access)
            clone.session._fork_pretreatment(state,clone.directory/'pulse.log');clone.casualty=CasualtyInput.model_validate(self.casualty.model_dump());clone.registry.register(clone.casualty)
            clone._prepared=True;clone._control_only=control_only;clone._baseline_volume=self._baseline_volume
            clone._write('fork_origin.json',{'parent_run':self.run_id,'state_sha256':hashlib.sha256(state.encode()).hexdigest(),'decision_s':660,'control_only':control_only})
            return clone
    def fork_control(self,directory,*,run_id):return self.fork_validation(directory,run_id=run_id,control_only=True)
    def restore_state(self,*args,**kwargs):
        self._deny('UNSUPPORTED_RECOVERY','Inactive hemothorax volume is not preserved; no state injection or post-treatment restore')
