"""Continuous, single-exposure engineering runtime. Not an admission pathway.

Only fixed native environment removal is executable, with explicit research,
observation and resource grants. Clinical goals remain unapproved, even when
native execution is confirmed. Old CaseRuntime and its whitelist are untouched.
"""
import copy,fcntl,hashlib,json,math,threading
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from core301.contracts.v2.exposure_validation import ExposureInput,EvacuationPlan,EvacuationResources,ExposureContext
from core301.pulse.observation_projector import REQUESTS,BASIC,ObservationProjector,ObservationAccess
from core301.pulse.v2.exposure_session import ExposureSession,PROFILES,PROFILE,environment_action,environment_signature
from .execution_journal import ExecutionJournal
from .errors import V2Error

PUBLIC_FIELDS=tuple(k for k in REQUESTS if not k.startswith('neurologic.'))
OPTIONAL=frozenset(set(PUBLIC_FIELDS)-set(BASIC))
# Reuse the existing project terminal/critical event names; never clinical ranges.
HALT_EVENTS=frozenset({'IrreversibleState','CardiacArrest','CardiovascularCollapse','CriticalBrainOxygenDeficit','HypovolemicShock'})

def safety_review(observation):
    """No clinical threshold is inferred from successful native execution."""
    events=copy.deepcopy(observation.native_events)
    return {'admission':'PENDING_RESEARCH_RULE_APPROVAL','goal_passed':False,
            'production_enabled':False,'native_events':events,
            'safety_disposition':'UNRESOLVED_EVENTS' if events else 'CRITERIA_NOT_APPROVED',
            'halt_required':bool(HALT_EVENTS.intersection(events))}

class ExposureValidationRuntime:
    def __init__(self,*,patient_id,run_id,directory,mode='production',validation_only=False,observation_access=False,resources=None):
        if mode!='research':raise V2Error('PRODUCTION_NOT_ENABLED','Exposure production is disabled')
        if validation_only is not True:raise V2Error('RESEARCH_RULE_APPROVAL_PENDING','Explicit engineering validation only')
        if not isinstance(patient_id,str) or not patient_id.strip() or not isinstance(run_id,str) or not run_id.strip():
            raise V2Error('INVALID_IDENTITY','Patient and run identity required')
        if resources is not None:
            resources=EvacuationResources.model_validate(resources)
            if (resources.patient_id,resources.run_id)!=(patient_id,run_id):raise V2Error('RESOURCE_IDENTITY_MISMATCH','Resources belong to another run/patient')
        self.patient_id=patient_id;self.run_id=run_id;self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True);self._file_lock=(self.directory/'exposure.lock').open('a')
        try:fcntl.flock(self._file_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self._file_lock.close();raise V2Error('SESSION_IN_USE','Another writer owns this directory')
        self.session_epoch=uuid4().hex;self._lock=threading.RLock()
        try:
            path=self.directory/'execution_journal.json'
            if path.exists() and json.loads(path.read_text()).get('exposure_profile')!=PROFILE:
                raise V2Error('JOURNAL_PROFILE_MISMATCH','Not an exposure validation journal')
            self.journal=ExecutionJournal(self.directory,run_id,patient_id,self.session_epoch)
            if not self.journal.reopened:
                self.journal.data.update(exposure_profile=PROFILE,admission='PENDING_RESEARCH_RULE_APPROVAL',goal_passed=False,resources=resources.model_dump() if resources else None)
                self.journal.flush()
            self._session=ExposureSession(patient_id,PUBLIC_FIELDS)
        except Exception:
            self._file_lock.close();raise
        self.resources=resources;self.observation_access=observation_access is True
        self._prepared=False;self._closed=False;self._halted=False;self._removed=False;self._control_only=False
        self._contexts={};self._source_signature=None;self._casualty=None;self._resource_state='AVAILABLE' if resources else 'UNAVAILABLE'
        self._projector=ObservationProjector()
        self._access=ObservationAccess(authorized=OPTIONAL,relevant=OPTIONAL,results_obtained=OPTIONAL) if self.observation_access else ObservationAccess()

    def _deny(self,code,message,request_id=None):
        self.journal.event(request_id,None,'REJECTED',None,error={'code':code,'message':message})
        raise V2Error(code,message)
    def _live(self):
        if self.journal.reopened:self._deny('RESTART_REQUIRES_RECOVERY','Restart is query-only')
        if self._closed or not self._prepared:self._deny('NOT_PREPARED','No live prepared exposure')
        if self._halted:self._deny('EXECUTION_HALTED','Prior execution uncertainty')
    def _write(self,name,value):
        (self.directory/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    def _capture(self):
        observation=self._session.exposure_observation(self._casualty.exposure_id,self.session_epoch)
        result={'patient_observation':self._projector.project(self.patient_id,self._session.get_simulation_time(),self._session.read_requested_data(),self._access).model_dump(),
                'exposure_observation':observation.model_dump(),'safety':safety_review(observation)}
        with (self.directory/'observations.jsonl').open('a') as f:f.write(json.dumps(result,allow_nan=False)+'\n')
        self.journal.data['last_observation']=result
        for record in self.journal.data['plans'].values():
            if record.get('status')=='EXECUTED':
                record['safety']=copy.deepcopy(result['safety'])
                record['last_observed_at_s']=observation.simulation_time_s
        if result['safety']['halt_required']:self._halted=True
        return result
    def _check_source(self):
        state=json.loads(self._session.serialize_state())
        if state.get('ActiveActions',{}).get('AnyAction') or state.get('Conditions',{}).get('AnyCondition') or state.get('AirwayMode','Free')!='Free' or state.get('Intubation','Off')!='Off':
            raise V2Error('UNREGISTERED_NATIVE_SOURCE','Unexpected patient/equipment/condition')
        if environment_signature(state)!=self._source_signature:
            raise V2Error('STALE_NATIVE_SOURCE','Actual exposure environment differs from registered source')
        return state
    def prepare(self,casualty):
        with self._lock:
            if self.journal.reopened:self._deny('RESTART_REQUIRES_RECOVERY','Restart cannot initialize')
            if self._prepared or self._closed or self._halted:self._deny('ALREADY_PREPARED','Use a new continuous session')
            try:casualty=ExposureInput.model_validate(casualty)
            except ValidationError as exc:self._deny('INVALID_EXPOSURE_SCHEMA',str(exc))
            if casualty.patient_id!=self.patient_id:self._deny('PATIENT_MISMATCH','Wrong patient')
            self._casualty=casualty;co,o2,healthy,pre,post=PROFILES[casualty.exposure_type]
            self._write('initialization.json',{'input':casualty.model_dump(),'profile':PROFILE,'healthy_s':healthy,'exposure_s':pre,'response_s':post,'payload':environment_action(co,o2)})
            try:
                self._session.initialize(self.directory/'pulse.log')
                (self.directory/'initial_state.json').write_text(self._session.serialize_state())
                self._capture()
                if self._halted:raise V2Error('NATIVE_CRITICAL_EVENT','Unsafe initial native event')
                for t in range(1,healthy+1):
                    self._session.advance_to(t);self._capture()
                    if self._halted:raise V2Error('NATIVE_CRITICAL_EVENT','Healthy preparation stopped on native event')
                self.journal.event(None,None,'EXPOSURE_SUBMITTED',float(healthy),payload=environment_action(co,o2))
                result=self._session._submit(environment_action(co,o2),'exposure')
                self.journal.event(None,None,'EXPOSURE_ACCEPTED',float(healthy),native_result=result)
                for t in range(healthy+1,healthy+pre+1):
                    self._session.advance_to(t);self._capture()
                    if self._halted:raise V2Error('NATIVE_CRITICAL_EVENT','Initialization stopped on native terminal/critical event')
                self._source_signature=environment_signature(json.loads(self._session.serialize_state()))
                self._check_source();self._prepared=True
                d=self._session.exposure_observation(casualty.exposure_id,self.session_epoch)
                established=(d.aorta_co_saturation.value is not None and d.aorta_co_saturation.value>0) if casualty.exposure_type=='carbon_monoxide_exposure' else 'Hypoxia' in d.native_events
                if not established:raise V2Error('TARGET_NOT_ESTABLISHED','Native exposure pathology absent')
                (self.directory/'pretreatment_state.json').write_text(self._session.serialize_state());self.journal.flush()
            except Exception as exc:
                self._halted=True;self._deny('INITIALIZATION_FAILED',str(exc))
            return self.observe()
    def observe(self):
        with self._lock:
            self._live()
            return self._projector.project(self.patient_id,self._session.get_simulation_time(),self._session.read_requested_data(),self._access)
    def exposure_observation(self):
        with self._lock:
            self._live()
            if not self.observation_access:self._deny('OBSERVATION_ACCESS_DENIED','Explicit co-oximetry/environment grant required')
            return self._session.exposure_observation(self._casualty.exposure_id,self.session_epoch)
    def build_context(self):
        with self._lock:
            self._live();ref=uuid4().hex
            context=ExposureContext(context_ref=ref,patient_id=self.patient_id,exposure_id=self._casualty.exposure_id,exposure_type=self._casualty.exposure_type,
                patient_observation=self.observe(),exposure_observation=self.exposure_observation() if self.observation_access else None,
                available_evacuation_teams=self.resources.evacuation_teams if self.resources and self._resource_state=='AVAILABLE' else 0)
            self._contexts[ref]=context.model_dump();return context
    def execute_plan(self,plan,*,request_id,context_ref):
        with self._lock:
            if not isinstance(request_id,str) or not request_id.strip():self._deny('INVALID_REQUEST_ID','Nonempty request required')
            try:plan=EvacuationPlan.model_validate(plan)
            except ValidationError as exc:self._deny('INVALID_PLAN_SCHEMA',str(exc),request_id)
            digest=hashlib.sha256(json.dumps(plan.model_dump(),sort_keys=True).encode()).hexdigest()
            old=self.query(request_id)
            if old:
                if old['plan_sha256']!=digest or old['context_ref']!=context_ref:self._deny('IDEMPOTENCY_CONFLICT','Changed payload/context',request_id)
                return old
            self._live()
            if plan.patient_id!=self.patient_id:self._deny('PATIENT_MISMATCH','Wrong patient',request_id)
            if plan.exposure_id!=self._casualty.exposure_id:self._deny('SOURCE_MISMATCH','Wrong exposure',request_id)
            if self._control_only:self._deny('CONTROL_BRANCH_ONLY','No control treatment',request_id)
            if self._removed:self._deny('ACTION_REPLAY_BLOCKED','Source already removed',request_id)
            if context_ref not in self._contexts:self._deny('CONTEXT_NOT_FOUND','Foreign or unknown context',request_id)
            now=self._session.get_simulation_time();_,_,healthy,pre,_=PROFILES[self._casualty.exposure_type]
            if abs(now-healthy-pre)>1e-6:self._deny('UNVALIDATED_TIMING','Only fixed decision time',request_id)
            context=ExposureContext.model_validate(self._contexts[context_ref])
            if context.patient_observation.simulation_time_s!=now:self._deny('STALE_CONTEXT','Observation is stale',request_id)
            if not self.observation_access or context.exposure_observation is None:self._deny('MONITORING_UNAVAILABLE','Missing exposure monitoring grant',request_id)
            for m in context.exposure_observation.model_dump().values():
                if isinstance(m,dict) and 'status' in m and m['status']!='available':self._deny('MONITORING_UNAVAILABLE','Missing current diagnostic',request_id)
            for field in PUBLIC_FIELDS:
                g,f=field.split('.');m=getattr(getattr(context.patient_observation,g),f)
                if m.status!='available' or m.observed_at_s!=now:self._deny('MONITORING_UNAVAILABLE','Missing physiology',request_id)
            try:self._check_source()
            except V2Error as exc:self._deny(exc.code,str(exc),request_id)
            r=self.resources
            if r is None or r.run_id!=self.run_id or r.patient_id!=self.patient_id or r.permission!='research_environment_removal':self._deny('RESOURCE_IDENTITY_MISMATCH','No matching authority',request_id)
            if self._resource_state!='AVAILABLE' or r.evacuation_teams<1 or not r.protected_route_available or not r.receiving_environment_verified:self._deny('RESOURCE_UNAVAILABLE','Team, route and destination are required',request_id)
            record={'request_id':request_id,'plan_sha256':digest,'context_ref':context_ref,'plan':plan.model_dump(),'actions':[],
                    'status':'RESERVED','resource_state':'RESERVED','goal_passed':False,'admission':'PENDING_RESEARCH_RULE_APPROVAL','production_enabled':False}
            self.journal.data['plans'][request_id]=record;self._resource_state='RESERVED';self.journal.event(request_id,None,'RESERVED',now,teams=1)
            item={'action_id':uuid4().hex,'submitted_time_s':now,'state':'SUBMITTED','lifecycle':'PENDING_NATIVE_RESULT','native_payload':environment_action(0,.21),'accepted':None}
            record['actions'].append(item);self.journal.event(request_id,item['action_id'],'SUBMITTED',now,payload=item['native_payload'])
            try:
                result=self._session._submit(item['native_payload'],'treatment');item.update(accepted=result['accepted'],native_result=result)
                self._session.advance_to(healthy+pre+.02)
                state=json.loads(self._session.serialize_state());new=environment_signature(state)
                expected=copy.deepcopy(self._source_signature);expected['AmbientGas']={'Nitrogen':1-.21-.0004,'Oxygen':.21,'CarbonDioxide':.0004,'CarbonMonoxide':0.0}
                if new!=expected:raise V2Error('REMOVAL_UNCONFIRMED','Native environment does not match destination')
                self._source_signature=new;self._check_source()
                self._removed=True;self._resource_state='DEPLOYED';record.update(status='EXECUTED',resource_state='DEPLOYED')
                item.update(state='COMPLETED',lifecycle='COMPLETED',meaning='environment_changed_only_not_clinical_recovery')
                record['safety']=self._capture()['safety'];self.journal.event(request_id,item['action_id'],'ENVIRONMENT_CONFIRMED',self._session.get_simulation_time())
            except Exception as exc:
                self._halted=True;self._resource_state='QUARANTINED';record.update(status='UNKNOWN',resource_state='QUARANTINED',error=str(exc))
                item.update(state='UNKNOWN',lifecycle='UNKNOWN');self.journal.event(request_id,item['action_id'],'UNKNOWN',None,error=str(exc))
                raise V2Error('EXECUTION_UNCERTAIN','No rollback or retry after native uncertainty') from exc
            return copy.deepcopy(record)
    def advance_to(self,target):
        with self._lock:
            self._live();_,_,healthy,pre,post=PROFILES[self._casualty.exposure_type];now=self._session.get_simulation_time()
            if type(target) not in (int,float) or not math.isfinite(target) or target<now or target>healthy+pre+post or abs(target-round(target))>1e-6:
                self._deny('UNVALIDATED_WINDOW','Use absolute integer seconds within fixed response window')
            try:
                self._check_source()
                while self._session.get_simulation_time()<target-1e-6:
                    next_s=min(target,math.floor(self._session.get_simulation_time()+1e-6)+1)
                    self._session.advance_to(next_s);snapshot=self._capture()
                    if self._halted:raise V2Error('NATIVE_CRITICAL_EVENT','Stop on native terminal/critical event')
                self._check_source();self.journal.flush()
            except Exception as exc:
                self._halted=True;self.journal.event(None,None,'ADVANCE_FAILED',None,error=str(exc));raise
            return self.observe()
    def fork_control(self,*,run_id,directory,control_only=True,resources=None):
        with self._lock:
            self._live();_,_,healthy,pre,_=PROFILES[self._casualty.exposure_type]
            if self._removed or self.journal.data['plans'] or abs(self._session.get_simulation_time()-healthy-pre)>1e-6:
                self._deny('CONTROL_FORK_SCOPE','Only untouched pretreatment state may fork')
            self._check_source();state=self._session.serialize_state()
            child=ExposureValidationRuntime(patient_id=self.patient_id,run_id=run_id,directory=directory,mode='research',validation_only=True,observation_access=self.observation_access,resources=resources)
            try:
                if child.journal.reopened:raise V2Error('RESTART_REQUIRES_RECOVERY','Fork needs new destination')
                child._casualty=ExposureInput.model_validate(self._casualty.model_dump());child._control_only=control_only
                child._session._fork_pretreatment(state,child.directory/'pulse.log',self._casualty.exposure_type)
                child._source_signature=copy.deepcopy(self._source_signature);child._prepared=True;child._check_source()
                before=self.observe().model_dump();after=child.observe().model_dump()
                if before!=after or self._session.diagnostics()!=child._session.diagnostics():raise V2Error('FORK_MISMATCH','Native pretreatment values changed')
                (child.directory/'initial_state.json').write_text(state);child._capture()
                child.journal.event(None,None,'PRETREATMENT_FORK',child._session.get_simulation_time(),parent_run=self.run_id,state_sha256=hashlib.sha256(state.encode()).hexdigest(),control_only=control_only)
                return child
            except Exception:child.close();raise
    def query(self,request_id):
        with self._lock:return self.journal.query(request_id)
    def restore_state(self,*args,**kwargs):
        with self._lock:self._deny('UNSUPPORTED_RECOVERY','External or posttreatment restoration is forbidden')
    def close(self):
        with self._lock:
            if not self._closed:
                if self._session.ready:(self.directory/'final_state.json').write_text(self._session.serialize_state())
                self._session.close();self._closed=True;fcntl.flock(self._file_lock,fcntl.LOCK_UN);self._file_lock.close()
