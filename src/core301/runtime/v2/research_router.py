"""Unified V2 research factory: legacy delegation plus fixed specialty routes.

No native payload, approval token, external observation or session injection is
accepted. Pending profiles can only enter explicitly requested validation mode.
"""
import copy,fcntl,json,math,hashlib,threading
from pathlib import Path
from uuid import uuid4
from core301.contracts.v2.exposure_validation import ExposureInput
from core301.contracts.v2.restricted_observation import RestrictedObservation
from core301.pulse.observation_projector import ObservationAccess, BASIC
from core301.pulse.v2.hemothorax_session import HemothoraxSession, _DrainNative, DRAIN_REQUESTS
from core301.runtime.v2.exposure_validation import ExposureValidationRuntime, PUBLIC_FIELDS, HALT_EVENTS
from core301.runtime.v2.hemothorax_validation import HemothoraxValidationRuntime
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.runtime.v2.restricted_registry import REGISTRY, VERSION
from core301.runtime.v2.restricted_acceptance import safety_check, mechanism_check
from core301.runtime.v2.errors import V2Error

class _SodiumDrainNative(_DrainNative):
    def _requests_json(self):
        p=json.loads(super()._requests_json())
        p['DataRequest'].append({'Category':'LiquidCompartment','CompartmentName':'Aorta','SubstanceName':'Sodium','PropertyName':'Molarity','Unit':'mEq/L'})
        return json.dumps(p)
    def _read(self):
        self._require_ready();v=self._engine.pull_data()
        if len(v)!=len(self.requested_fields)+len(DRAIN_REQUESTS)+2 or not math.isfinite(v[0]):
            raise V2Error('NATIVE_DATA_SHAPE','Invalid sodium/drainage read')
        return v

class _GuardedHemoSession(HemothoraxSession):
    """Same native engine, monitor actual events during every advancement."""
    def __init__(self,patient_id,requested_fields):
        super().__init__(patient_id,requested_fields)
        self._native=_SodiumDrainNative(patient_id,requested_fields=requested_fields)
    def sodium(self):
        v=float(self._native._read()[-1]);now=self.get_simulation_time()
        return {'value':v if math.isfinite(v) else None,'status':'available' if math.isfinite(v) else 'unavailable','observed_at_s':now}
    def _safety_sample(self):
        events=self.active_events()
        values={k:v.value for k,v in self.read_requested_data().items()};values['Na']=self.sodium()['value']
        with (self._log_path.parent/'native_safety.jsonl').open('a') as f:
            f.write(json.dumps({'time_s':self.get_simulation_time(),'native_events':events,'values':values},allow_nan=False)+'\n')
        if HALT_EVENTS.intersection(events):raise V2Error('NATIVE_CRITICAL_EVENT','Existing terminal/critical veto')
    def initialize(self,log_path,configuration=None):
        super().initialize(log_path,configuration);self._safety_sample()
        (self._log_path.parent/'initial_state.json').write_text(self.serialize_state())
    def advance_time(self, seconds):
        ticks=round(seconds/.02)
        if seconds<0 or abs(ticks*.02-seconds)>1e-6:raise V2Error('INVALID_TIME','Native tick alignment required')
        for i in range(ticks):
            if not self._native.advance_step():raise V2Error('NATIVE_ADVANCE_FAILED','Pulse stopped')
            if (i+1)%50==0 or i==ticks-1:
                self._safety_sample()

class _GuardedHemothorax(HemothoraxValidationRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.session=_GuardedHemoSession(self.patient_id,(*BASIC,*sorted(self.access.visible())))


def open_research_case(injury_type, *, patient_id, run_id, directory, mode='production', validation_only=False,
                       resources=None, access=None, specialty_access=False):
    """Backend API. Agent supplies plans only; caller owns grants and resources."""
    if mode!='research':raise V2Error('PRODUCTION_NOT_ENABLED','All V2 profiles are research only')
    if injury_type not in REGISTRY:raise V2Error('INJURY_NOT_OPEN','Unknown research profile')
    if type(validation_only) is not bool:raise V2Error('INVALID_MODE','Boolean validation_only required')
    if REGISTRY[injury_type].admission=='ADMITTED_LEGACY':
        return CaseRuntime(patient_id,directory,run_id=run_id,mode=mode,resources=resources,access=access)
    if REGISTRY[injury_type].admission=='PENDING' and not validation_only:
        raise V2Error('ADMISSION_PENDING',REGISTRY[injury_type].blocker)
    if injury_type in ('hemothorax','carbon_monoxide_exposure') and not validation_only:
        from core301.runtime.v2.restricted_risk import reference
        reference(injury_type)  # Check pinned authorization/evidence before any files or engine.
    if not validation_only:
        from core301.runtime.v2.restricted_admission import verify_admission
        if verify_admission(injury_type)!=REGISTRY[injury_type].profile:raise V2Error('ADMISSION_EVIDENCE_INVALID','Registry profile mismatch')
    return RestrictedCaseRuntime(injury_type,patient_id=patient_id,run_id=run_id,directory=directory,
        validation_only=validation_only,resources=resources,access=access,specialty_access=specialty_access)

class RestrictedCaseRuntime:
    def __init__(self,kind,*,patient_id,run_id,directory,validation_only,resources,access,specialty_access):
        if kind not in REGISTRY or REGISTRY[kind].admission=='ADMITTED_LEGACY':raise V2Error('INJURY_NOT_OPEN','Specialty route required')
        if type(validation_only) is not bool or REGISTRY[kind].admission=='PENDING' and not validation_only:
            raise V2Error('ADMISSION_PENDING','Explicit validation mode required')
        self.kind=kind;self.profile=REGISTRY[kind];self.patient_id=patient_id;self.run_id=run_id
        self.directory=Path(directory);self.validation_only=validation_only;self._lock=threading.RLock()
        self._history=[];self._prehistory=[];self._closed=False;self._control=False;self._pair=None;self._prepared=False
        self._specialty_access=specialty_access is True;self._access=access
        self.directory.mkdir(parents=True,exist_ok=True)
        self._file_lock=(self.directory/'restricted.lock').open('a')
        try:fcntl.flock(self._file_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self._file_lock.close();raise V2Error('SESSION_IN_USE','Concurrent restricted writer')
        try:
            manifest=self.directory/'restricted_route.json'
            identity={'version':VERSION,'kind':kind,'patient_id':patient_id,'run_id':run_id,'validation_only':validation_only,'production_enabled':False}
            if manifest.exists():
                if json.loads(manifest.read_text())!=identity:raise V2Error('ROUTE_IDENTITY_MISMATCH','Journal route/mode mismatch')
            elif any(p.name!='restricted.lock' for p in self.directory.iterdir()):
                raise V2Error('DIRECTORY_NOT_EMPTY','Use a new owned directory')
            else:manifest.write_text(json.dumps(identity,indent=2)+'\n')
            if kind=='hemothorax':
                self._backend=_GuardedHemothorax(patient_id,self.directory,run_id=run_id,mode='research',validation_only=True,
                    drainage_access=specialty_access,access=access,resources=resources)
            else:
                self._backend=ExposureValidationRuntime(patient_id=patient_id,run_id=run_id,directory=self.directory/('execution' if (self.directory/'execution').exists() else 'preparation'),mode='research',validation_only=True,
                    observation_access=specialty_access,resources=resources)
        except Exception:self._file_lock.close();raise
    @property
    def _session(self):return self._backend.session if self.kind=='hemothorax' else self._backend._session
    def _live(self):
        if self._closed or not self._prepared:raise V2Error('NOT_PREPARED','No live prepared case')
        if self._backend._halted:raise V2Error('EXECUTION_HALTED','Prior uncertainty or critical event')
    def prepare(self,casualty):
        with self._lock:
            if self.kind!='hemothorax':
                c=ExposureInput.model_validate(casualty)
                if c.exposure_type!=self.kind:raise V2Error('ROUTE_IDENTITY_MISMATCH','Exposure differs from registered route')
            self._backend.prepare(casualty);self._prepared=True
            if self.kind!='hemothorax':
                for line in (self._backend.directory/'observations.jsonl').read_text().splitlines():
                    x=json.loads(line);self._prehistory.append(RestrictedObservation(injury_type=self.kind,patient_id=self.patient_id,session_epoch=self._backend.session_epoch,
                        patient_observation=x['patient_observation'],specialty=x['exposure_observation'],aorta_sodium_mEq_L=x['exposure_observation']['aorta_sodium_mEq_L'],native_events=x['exposure_observation']['native_events']))
                # The verified exposure profile starts treatment from its owned
                # pretreatment checkpoint. Native reload affects early dynamics,
                # so continuous-original and checkpoint execution are not merged.
                parent=self._backend
                try:
                    child=parent.fork_control(run_id=self.run_id,directory=self.directory/'execution',control_only=False,resources=parent.resources)
                except Exception:
                    self._prepared=False;raise
                finally:parent.close()
                self._backend=child
                child.journal.event(None,None,'FIXED_PRETREATMENT_CHECKPOINT_PROFILE',self.profile.decision_s,
                    preparation_directory=str(parent.directory),external_state_input=False)
            (self.directory/'prepared_state.json').write_text(self._session.serialize_state())
            self._capture();return self.observe()
    def observe(self):
        with self._lock:self._live();return self._backend.observe()
    def specialty_observation(self):
        with self._lock:
            self._live()
            return self._backend.drainage_observation() if self.kind=='hemothorax' else self._backend.exposure_observation()
    def build_context(self,**kwargs):
        with self._lock:self._live();return self._backend.build_context(**kwargs)
    def observation(self):
        with self._lock:
            self._live()
            return RestrictedObservation(injury_type=self.kind,patient_id=self.patient_id,session_epoch=self._backend.session_epoch,
                patient_observation=self.observe(),specialty=self.specialty_observation(),aorta_sodium_mEq_L=self._sodium(),native_events=self._session.active_events())
    def _sodium(self):
        return self._session.sodium() if self.kind=='hemothorax' else self._session.exposure_observation(self._backend._casualty.exposure_id,self._backend.session_epoch).aorta_sodium_mEq_L
    def _capture(self):
        # Backend-only capture never grants extra fields to the Agent.
        b=self._backend;p=b.observe()
        s=b.session.drainage(b.session_epoch) if self.kind=='hemothorax' else b._session.exposure_observation(b._casualty.exposure_id,b.session_epoch)
        x=RestrictedObservation(injury_type=self.kind,patient_id=self.patient_id,session_epoch=b.session_epoch,
            patient_observation=p,specialty=s,aorta_sodium_mEq_L=self._sodium(),native_events=self._session.active_events())
        self._history.append(x)
        with (self.directory/'restricted_observations.jsonl').open('a') as f:f.write(x.model_dump_json()+'\n')
        if HALT_EVENTS.intersection(x.native_events):
            b._halted=True;b.journal.event(None,None,'NATIVE_CRITICAL_EVENT',x.patient_observation.simulation_time_s,events=x.native_events)
            raise V2Error('NATIVE_CRITICAL_EVENT','Existing severe event veto')
        return x
    def _execution_monitoring(self,request_id):
        now=self._session.get_simulation_time();p=self._backend.observe().model_dump()
        sodium=self._sodium();sodium=sodium.model_dump() if hasattr(sodium,'model_dump') else sodium
        measurements=[sodium]
        for path in PUBLIC_FIELDS:
            group,field=path.split('.');measurements.append((p.get(group) or {}).get(field,{}))
        if any(m.get('status')!='available' or m.get('value') is None or m.get('observed_at_s')!=now for m in measurements):
            self._backend._deny('MONITORING_UNAVAILABLE','All fixed physiology and sodium requests must be current',request_id)
        from core301.runtime.v2.restricted_acceptance import CYCLE_EVENTS,TARGET_EVENTS
        expected=CYCLE_EVENTS | (TARGET_EVENTS if self.kind=='environmental_hypoxia' else {'MinimalHemothorax'} if self.kind=='hemothorax' else set())
        if self.kind in ('hemothorax','carbon_monoxide_exposure'):
            from core301.runtime.v2.restricted_risk import verify_risk_scope
            verify_risk_scope();expected=expected|{'Hypernatremia'}
        if set(self._session.active_events())-expected:
            self._backend._deny('UNRESOLVED_NATIVE_EVENTS','Unexpected native event before treatment',request_id)
    def execute_plan(self,plan,*,request_id,context_ref):
        with self._lock:
            # Preserve underlying durable idempotent query, including UNKNOWN.
            old=self._backend.query(request_id)
            if not old:
                self._live();self._execution_monitoring(request_id)
            if self.kind=='hemothorax' and not old:
                from core301.contracts.v2.treatment import TreatmentPlan
                p=TreatmentPlan.model_validate(plan)
                if [a.action_type for a in p.actions]!=['control_hemothorax_bleeding','chest_tube']:
                    self._backend._deny('ACTION_NOT_OPEN','Unified profile requires source control then tube',request_id)
            result=self._backend.execute_plan(plan,request_id=request_id,context_ref=context_ref)
            if not old:
                if self.kind=='hemothorax':self._backend.advance(.02)
                self._capture()
            return self._backend.query(request_id)
    def advance_to(self,target):
        with self._lock:
            self._live();now=self._session.get_simulation_time()
            if type(target) not in (int,float) or not math.isfinite(target) or target<now or target>self.profile.end_s or target!=round(target):
                raise V2Error('UNVALIDATED_WINDOW','Absolute integer time within fixed profile required')
            if self.kind!='hemothorax':
                self._backend.advance_to(target)
                # Reuse every native 1 Hz backend snapshot without advancing a
                # second time or repeatedly serializing a large native state.
                with (self.directory/'restricted_observations.jsonl').open('a') as output:
                    for line in (self._backend.directory/'observations.jsonl').read_text().splitlines():
                        x=json.loads(line);p=x['patient_observation'];s=x['exposure_observation']
                        if p['simulation_time_s']<=now+1e-6:continue
                        obs=RestrictedObservation(injury_type=self.kind,patient_id=self.patient_id,session_epoch=self._backend.session_epoch,
                            patient_observation=p,specialty=s,aorta_sodium_mEq_L=s['aorta_sodium_mEq_L'],native_events=s['native_events'])
                        self._history.append(obs);output.write(obs.model_dump_json()+'\n')
            else:
                while self._session.get_simulation_time()<target-1e-6:
                    next_s=min(target,math.floor(self._session.get_simulation_time()+1e-6)+1)
                    self._backend.advance(next_s-self._session.get_simulation_time());self._capture()
            return self.observe()
    def fork_control(self,*,run_id,directory):
        """Matched untreated comparator, backend-owned and never Agent-injected."""
        with self._lock:
            self._live()
            if self._pair is not None:raise V2Error('CONTROL_FORK_SCOPE','One matched comparator per case')
            path=Path(directory)
            if path.exists() and any(path.iterdir()):raise V2Error('DIRECTORY_NOT_EMPTY','Comparator requires new directory')
            b=self._backend
            child=b.fork_control(path,run_id=run_id) if self.kind=='hemothorax' else b.fork_control(run_id=run_id,directory=path)
            # Private wrapper creation around an already validated owned native fork.
            c=object.__new__(RestrictedCaseRuntime)
            c.__dict__.update(kind=self.kind,profile=self.profile,patient_id=self.patient_id,run_id=run_id,directory=path,
                validation_only=self.validation_only,_backend=child,_lock=threading.RLock(),_history=[],_prehistory=[],_closed=False,
                _control=True,_pair=self,_prepared=True,_specialty_access=self._specialty_access,_access=self._access,_file_lock=None)
            c._capture();self._pair=c
            a=self._history[0].model_dump();z=c._history[0].model_dump()
            a.pop('session_epoch');z.pop('session_epoch');a['specialty'].pop('session_epoch');z['specialty'].pop('session_epoch')
            if a!=z:
                c.close();self._pair=None;raise V2Error('FORK_MISMATCH','Comparator observations changed')
            b.journal.event(None,None,'RESTRICTED_COMPARATOR',self.profile.decision_s,control_run=run_id)
            return c
    def acceptance(self):
        with self._lock:
            self._live()
            p=self.profile
            if self._control or self._pair is None or self._pair._closed:raise V2Error('MATCHED_CONTROL_REQUIRED','Live backend-owned comparator required')
            if abs(self._session.get_simulation_time()-p.end_s)>1e-6 or abs(self._pair._session.get_simulation_time()-p.end_s)>1e-6:
                raise V2Error('INCOMPLETE_FIXED_WINDOW','Both branches must reach the preregistered endpoint')
            risk=None
            if self.kind in ('hemothorax','carbon_monoxide_exposure'):
                from core301.runtime.v2.restricted_risk import conformance
                presamples=[json.loads(line) for line in (self.directory/'native_safety.jsonl').read_text().splitlines()] if self.kind=='hemothorax' else []
                risk=conformance(self.kind,self._prehistory+self._history,presamples)
            self._backend._check_source();self._pair._backend._check_source()
            if self.observation()!=self._history[-1] or self._pair.observation()!=self._pair._history[-1]:
                raise V2Error('STALE_OBSERVATION','Native state changed after the recorded endpoint')
            safety=safety_check(self.kind,self._prehistory+self._history,risk_conformance=risk)
            if self.kind=='hemothorax':
                from core301.runtime.v2.restricted_acceptance import CYCLE_EVENTS
                preevents=set().union(*(set(x['native_events']) for x in presamples))
                unexpected=preevents-CYCLE_EVENTS-{'MinimalHemothorax','Hypernatremia'}
                safety['all_event_names']=sorted(set(safety['all_event_names'])|preevents)
                if unexpected:
                    safety['passed']=False;safety['reasons'].append('UNRESOLVED_PRETREATMENT_EVENT')
            mechanism={'passed':False,'reason':'INCOMPLETE_OBSERVATIONS'}
            if not any(x.startswith('MISSING') for x in safety['reasons']):mechanism=mechanism_check(self.kind,self._history,self._pair._history)
            executions=self._backend.journal.data['plans'].values()
            actions=[a for r in executions for a in r.get('actions',[])]
            executed=bool(actions) and all(a.get('accepted') is True and a.get('state') not in ('UNKNOWN','FAILED') for a in actions)
            passed=bool(executed and mechanism['passed'] and safety['passed'])
            state=self._session.serialize_state()
            (self.directory/'accepted_endpoint_state.json').write_text(state)
            result={'evaluated_at_s':self._session.get_simulation_time(),'session_epoch':self._backend.session_epoch,
                'native_endpoint_state_sha256':hashlib.sha256(state.encode()).hexdigest(),'version':VERSION,'injury_type':self.kind,'profile':p.profile,'route_admission':p.admission,
                'mechanism':mechanism,'safety':safety,'execution_confirmed':executed,'engineering_case_passed':passed,
                'restricted_case_passed':passed and p.admission.startswith('ADMITTED') and not self.validation_only,
                'validation_only':self.validation_only,'production_enabled':False,'clinical_efficacy':'NOT_EVALUATED',
                'user_final_acceptance':'NOT_RECORDED','control_run':self._pair.run_id}
            (self.directory/'restricted_acceptance.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            self._backend.journal.data['restricted_acceptance']=copy.deepcopy(result);self._backend.journal.flush()
            return result
    def query(self,request_id):return self._backend.query(request_id)
    def restore_state(self,*args,**kwargs):return self._backend.restore_state(*args,**kwargs)
    def close(self):
        with self._lock:
            if not self._closed:
                if self._session.ready:(self.directory/'final_state.json').write_text(self._session.serialize_state())
                self._backend.close();self._closed=True
                if self._file_lock:self._file_lock.close()
