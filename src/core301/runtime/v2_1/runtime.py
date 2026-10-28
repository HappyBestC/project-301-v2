"""Single-session fixed composite execution, durable intent and fail-closed ownership."""
import copy,fcntl,hashlib,json,os,threading
from pathlib import Path
from uuid import uuid4
from .registry import lookup,VERSION
from .contracts import CompositePlan
from .resources import Resources
from .adapters import action_payload,kinds_for
from .native_backend import CompositeEngine
from .admission import verify_admission
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.exposure_validation import HALT_EVENTS,PUBLIC_FIELDS
from core301.pulse.v2.session import native_scalar
from core301.pulse.v2.exposure_session import environment_signature
from core301.contracts.casualty import TEMPLATES

def open_research_composite_case(pattern_id,*,patient_id,run_id,directory,mode='production',validation_only=False,observation_access=False,resources=None):
 if mode!='research':raise V2Error('PRODUCTION_NOT_ENABLED','V2.1 production disabled')
 if type(validation_only) is not bool or type(observation_access) is not bool:raise V2Error('INVALID_MODE','Explicit bool grants required')
 index,pattern=lookup(pattern_id)
 if not validation_only:verify_admission(pattern_id)
 return CompositeCase(index,pattern,patient_id,run_id,directory,validation_only,observation_access,resources)

class CompositeCase:
 def __init__(self,index,pattern,patient_id,run_id,directory,validation_only,observation_access,resources):
  if not all(isinstance(v,str) and v.strip() for v in (patient_id,run_id)):raise V2Error('INVALID_IDENTITY','Nonblank identity required')
  self.index=index;self.pattern=pattern;self.patient_id=patient_id;self.run_id=run_id;self.validation_only=validation_only;self.access=observation_access
  self._identity=(index,patient_id,run_id,validation_only);self._profile_digest=hashlib.sha256(json.dumps(pattern,sort_keys=True).encode()).hexdigest()
  self.resources=Resources(resources,run_id,patient_id);self.directory=Path(directory);self._mutex=threading.RLock();self._engine=None;self._prepared=False;self._halted=False;self._closed=False;self._contexts={};self._controlled=set();self._executed=[];self._removed=False
  self.directory.mkdir(parents=True,exist_ok=True)
  existing=list(self.directory.iterdir())
  if existing and not (self.directory/'journal.json').exists():raise V2Error('FOREIGN_DIRECTORY','Cannot reuse an unrelated case directory')
  self._file_lock=(self.directory/'case.lock').open('a')
  try:fcntl.flock(self._file_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError:self._file_lock.close();raise V2Error('SESSION_IN_USE','Case already owned')
  self._reopened=(self.directory/'journal.json').exists()
  try:
   if self._reopened:
    self.journal=json.loads((self.directory/'journal.json').read_text())
    if (self.journal['patient_id'],self.journal['run_id'],self.journal['pattern_id'],self.journal['version'],self.journal['validation_only'])!=(patient_id,run_id,pattern['pattern_id'],VERSION,validation_only):raise V2Error('JOURNAL_IDENTITY_MISMATCH','Wrong case identity/profile/mode')
   else:
    self.journal={'version':VERSION,'patient_id':patient_id,'run_id':run_id,'pattern_id':pattern['pattern_id'],'epoch':uuid4().hex,'validation_only':validation_only,'production_enabled':False,'requests':{},'events':[]};self._flush()
  except Exception:self._file_lock.close();raise
 def _flush(self):
  tmp=self.directory/'journal.tmp'
  with tmp.open('w') as f:json.dump(self.journal,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,self.directory/'journal.json')
  fd=os.open(self.directory,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 def _event(self,state,**kw):
  self.journal['events'].append({'state':state,**kw});self._flush()
 def _deny(self,code,message):
  self._event('REJECTED',code=code,message=message);raise V2Error(code,message)
 def _fixed_profile(self):
  _,canonical=lookup(self.pattern['pattern_id'])
  if (self.index,self.patient_id,self.run_id,self.validation_only)!=self._identity or self.pattern!=canonical or hashlib.sha256(json.dumps(self.pattern,sort_keys=True).encode()).hexdigest()!=self._profile_digest:self._deny('PROFILE_OR_IDENTITY_CHANGED','Case binding and fixed profile are immutable')
 def _live(self):
  self._fixed_profile()
  if self._reopened:self._deny('RESTART_QUERY_ONLY','Native recovery is unsupported')
  if self._closed or not self._prepared:self._deny('NOT_PREPARED','No active composite patient')
  if self._halted:self._deny('EXECUTION_HALTED','Uncertain/failed execution quarantined')
 def prepare(self):
  with self._mutex:
   self._fixed_profile()
   if self._prepared or self._closed or self._reopened:self._deny('INITIALIZATION_FORBIDDEN','No repeated initialization or restoration')
   if not self.access:self._deny('OBSERVATION_NOT_AUTHORIZED','All study measurements need explicit host access')
   if self._engine is not None:self._deny('INITIALIZATION_FORBIDDEN','An initialization attempt already occurred')
   try:
    self._engine=CompositeEngine(self.index,'runtime',self.directory/'native',self.patient_id)
    self._engine.prepare();self._prepared=True;self._condition_signature=json.loads(self._engine.session.serialize_state()).get('Conditions',{})
    self._guard();self._event('PREPARED',time_s=self._time());return self.observe()
   except Exception as e:self._halted=True;self._event('INITIALIZATION_FAILED',error=str(e));raise
 def _time(self):return self._engine.session.get_simulation_time()
 def _guard(self):
  s=self._engine.session;state=json.loads(s.serialize_state());actual=[]
  injury_names={t['pulse_action'] for t in TEMPLATES.values()}|{'ImpairedAlveolarExchangeExacerbation'}
  for wrapper in state.get('ActiveActions',{}).get('AnyAction',[]):
   for name,body in wrapper.get('PatientAction',{}).items():
    if name in injury_names:
     actual.append((name,body.get('Side'),body.get('Compartment'),body.get('Type','External' if name=='Hemorrhage' else 'Open' if name=='TensionPneumothorax' else None),native_scalar(body,'Severity')))
    elif name not in {'ChestOcclusiveDressing','NeedleDecompression','TubeThoracostomy','SubstanceCompoundInfusion','SupplementalOxygen','Intubation'}:self._deny('UNREGISTERED_NATIVE_SOURCE','Unexpected native patient action '+name)
  expected=[]
  for c in self.pattern['component_injuries']:
   kind=c['injury_type']
   if kind in self._controlled or kind in ('dehydration','carbon_monoxide_exposure','environmental_hypoxia'):continue
   if kind=='impaired_alveolar_exchange':name='ImpairedAlveolarExchangeExacerbation';typ=None
   else:
    t=TEMPLATES[kind];name=t['pulse_action'];typ=t['fixed'].get('Type')
   expected.append((name,c.get('side'),c.get('compartment'),typ,c['severity']))
  if sorted(actual,key=str)!=sorted(expected,key=str):self._deny('UNREGISTERED_NATIVE_SOURCE','Native injury identities/parameters differ from composite registry')
  from .device_guard import validate_devices
  validate_devices(state,self._executed,self._time(),self.pattern['simulation_timeline']['decision_s'])
  if state.get('Conditions',{})!=self._condition_signature:self._deny('CONDITION_CHANGED','Condition cannot be replaced')
  env=self.pattern['environment_profile'];co,o2=(0,.21) if self._removed or not env else (env['co'],env['oxygen'])
  gases=environment_signature(state)['AmbientGas']
  if gases.get('CarbonMonoxide',0)!=co or gases.get('Oxygen')!=o2:self._deny('ENVIRONMENT_CHANGED','Unregistered environment state')
  raw=s.read_requested_data();diag=s.diagnostics()
  from .native_backend import COMMON
  if set(raw)!=set(PUBLIC_FIELDS) or any(x.value is None or not __import__('math').isfinite(x.value) or abs(x.observed_at_s-self._time())>1e-7 for x in raw.values()) or any(diag.get(k) is None or not __import__('math').isfinite(diag[k]) for k,_ in COMMON):self._deny('MISSING_OBSERVATION','Critical measurement unavailable')
  if HALT_EVENTS.intersection(s.active_events()):self._halted=True;self._deny('NATIVE_CRITICAL_EVENT','Existing critical event veto')
 def observe(self):
  with self._mutex:
   self._live();self._guard();row=self._engine.capture()
   return {'version':'301.v2_1.observation.1','patient_id':self.patient_id,'pattern_id':self.pattern['pattern_id'],'session_epoch':self.journal['epoch'],'native':copy.deepcopy(row),'production_enabled':False,'clinical_safety':'NOT_EVALUATED'}
 def context(self):
  with self._mutex:
   obs=self.observe();ref=uuid4().hex;self._contexts[ref]=self._time();return {'context_ref':ref,'observation':obs}
 def query(self,request_id):
  with self._mutex:
   record=copy.deepcopy(self.journal['requests'].get(request_id))
   if record and self._reopened and record['state'] not in ('COMPLETED','REJECTED'):record['state']='UNKNOWN'
   return record
 def execute(self,plan,*,request_id,context_ref):
  with self._mutex:
   try:p=CompositePlan.model_validate(plan)
   except Exception as e:self._deny('INVALID_PLAN',str(e))
   if not isinstance(request_id,str) or not request_id.strip():self._deny('INVALID_REQUEST_ID','Nonblank request ID required')
   digest=hashlib.sha256(p.model_dump_json().encode()).hexdigest();old=self.query(request_id)
   if old:
    if old['digest']!=digest:self._deny('IDEMPOTENCY_CONFLICT','Request ID reused with different payload')
    return old
   self._live()
   if (p.patient_id,p.pattern_id)!=(self.patient_id,self.pattern['pattern_id']):self._deny('PATIENT_OR_PATTERN_MISMATCH','Wrong target')
   if not self.validation_only and p.bundle!='AB':self._deny('BUNDLE_NOT_ADMITTED','Only the jointly validated AB bundle has formal admission')
   if context_ref not in self._contexts or abs(self._contexts[context_ref]-self._time())>1e-7:self._deny('STALE_CONTEXT','Context is foreign or stale')
   if abs(self._time()-self.pattern['simulation_timeline']['decision_s'])>1e-6:self._deny('OUTSIDE_WINDOW','Fixed decision tick required')
   if self._executed:self._deny('EPISODE_ALREADY_TREATED','A second treatment episode is forbidden')
   self._guard();kinds=kinds_for(self.pattern,p.bundle)
   from core301.contracts.v2.treatment import CONFLICTS
   if any(a in kinds and b in kinds for a,b in CONFLICTS):self._deny('ACTION_CONFLICT','Fixed group contains conflicting devices/support')
   record={'digest':digest,'plan':p.model_dump(),'state':'PROPOSED','actions':[]};self.journal['requests'][request_id]=record;self._flush()
   try:record['resources']=self.resources.reserve(kinds)
   except Exception as e:record.update(state='REJECTED',error=str(e));self._flush();raise
   record['state']='RESERVED';self._flush()
   try:
    for kind in kinds:
     self._guard()
     if kind=='mechanical_ventilation' and 'intubation' not in self._executed:raise V2Error('DEPENDENCY_FAILED','Intubation not confirmed')
     if kind=='chest_tube' and 'control_hemothorax_bleeding' not in self._executed:raise V2Error('DEPENDENCY_FAILED','Hemothorax source not controlled')
     allocation=self.resources.begin(kind);item={'kind':kind,'state':'SUBMITTING','time_s':self._time(),'payload':action_payload(kind,self.pattern),'allocation':allocation};record['actions'].append(item);record['state']='SUBMITTING';self._flush()
     self._engine.submit(item['payload'],'treatment:'+kind)
     if kind.startswith('control_'):
      self._controlled.add({'control_external_bleeding':'external_hemorrhage','control_internal_bleeding':'abdominal_internal_hemorrhage','control_hemothorax_bleeding':'hemothorax'}[kind])
     if kind=='remove_from_exposure':self._removed=True
     self._engine.advance(self._time()+.02)
     self._executed.append(kind);self._guard();item['state']='NATIVE_ACCEPTED';item['confirmed_time_s']=self._time();allocation['delivery']='NATIVE_ACCEPTED_NOT_FULL_DOSE';self._flush()
    record['state']='COMPLETED';self._flush();self._contexts.clear();return copy.deepcopy(record)
   except Exception as e:
    self._halted=True;record.update(state='UNKNOWN',error=str(e));self._flush();raise
 def advance_to(self,time_s):
  with self._mutex:
   self._live();self._guard()
   if type(time_s) not in (int,float) or not __import__('math').isfinite(time_s) or time_s<self._time()-1e-7 or time_s>self.pattern['simulation_timeline']['end_s']+1e-7:self._deny('INVALID_TIME','Outside fixed forward observation window')
   try:self._engine.advance(time_s);self._guard()
   except Exception as e:self._halted=True;self._event('ADVANCE_FAILED',error=str(e));raise
   return self.observe()
 def acceptance(self):
  with self._mutex:
   from .acceptance_v2 import evaluate
   return evaluate(self)
 def restore_state(self,*args,**kwargs):self._deny('UNSUPPORTED_RECOVERY','No composite state restoration')
 def close(self):
  with self._mutex:
   if self._closed:return
   if self._engine:self._engine.close()
   self.resources.close();self._closed=True;self.journal['case_closed']=True;self._flush();self._file_lock.close()
