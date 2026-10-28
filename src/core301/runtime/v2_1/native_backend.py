"""Version 1: continuous, independent native composite branches; never restore state."""
import json,math,time,hashlib,sys,traceback
from pathlib import Path
from core301.pulse.session import PulseSession
from core301.pulse.v2.session import ResearchPulseSession,DIAGNOSTICS
from core301.pulse.v2.exposure_session import EXPOSURE_REQUESTS,environment_action
from core301.pulse.v2.hemothorax_session import DRAIN_REQUESTS
from core301.pulse.v2.injury_adapter import InjuryAdapter,PatientInitializer
from core301.contracts.v2.injury import CasualtyInput
from core301.pulse.injury_adapter import scalar
from core301.pulse.observation_projector import ObservationProjector,ObservationAccess,BASIC
from core301.runtime.v2.exposure_validation import PUBLIC_FIELDS,HALT_EVENTS
from core301.paths import PROJECT_ROOT as R
from .registry import patterns
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def diag_request(name,prop,unit):return name,{'Category':'Physiology','PropertyName':prop,'Unit':unit}
COMMON=DIAGNOSTICS+EXPOSURE_REQUESTS+(diag_request('total_fluid_mL','TotalFluidVolume','mL'),diag_request('alveolar_ventilation_L_min','TotalAlveolarVentilation','L/min'),('left_pleural_pressure_cmH2O',{'Category':'GasCompartment','CompartmentName':'LeftPleuralCavity','PropertyName':'Pressure','Unit':'cmH2O'}),('left_pleural_volume_mL',{'Category':'GasCompartment','CompartmentName':'LeftPleuralCavity','PropertyName':'Volume','Unit':'mL'}))
class Native(PulseSession):
 def __init__(self,pid,extra):super().__init__(pid,requested_fields=PUBLIC_FIELDS);self.extra=extra
 def _requests_json(self):
  p=json.loads(super()._requests_json());p['DataRequest'].extend(x[1] for x in self.extra);return json.dumps(p)
 def _read(self):
  self._require_ready();v=self._engine.pull_data()
  if len(v)!=1+len(PUBLIC_FIELDS)+len(self.extra):raise RuntimeError('DATA_SHAPE')
  return v
class Session(ResearchPulseSession):
 def __init__(self,pid,extra):super().__init__(pid,PUBLIC_FIELDS);self._native=Native(pid,extra)
 def diagnostics(self):
  v=self._native._read()[1+len(PUBLIC_FIELDS):];return {k:float(x) if math.isfinite(x) else None for (k,_),x in zip(self._native.extra,v)}
class CompositeEngine:
 def __init__(self,index,branch,directory,patient_id):
  self.pattern=patterns()[index];self.branch=branch;self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False);self.index=index
  self.pid=patient_id;self.session=Session(self.pid,COMMON+(DRAIN_REQUESTS if index==0 else ()));self.rows=[];self.events=set();self.actions=[];self.last_events=None
  optional=frozenset(set(PUBLIC_FIELDS)-set(BASIC));self.access=ObservationAccess(optional,optional,optional)
  dump(self.directory/'configuration.json',self.pattern);dump(self.directory/'requests.json',json.loads(self.session._native._requests_json()))
  dump(self.directory/'provenance.json',{'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'pulse_binary_sha256':hashlib.sha256((R/'pulse/bin/PyPulse.cpython-311-x86_64-linux-gnu.so').read_bytes()).hexdigest(),'production_enabled':False,'branch':branch,'continuous_native_session':True})
 def capture(self):
  s=self.session;now=s.get_simulation_time();raw=s.read_requested_data();obs=ObservationProjector().project(self.pid,now,raw,self.access).model_dump()
  row={'time_s':now,'patient_id':self.pid,'values':{k:x.value if math.isfinite(x.value) else None for k,x in raw.items()},'diagnostics':s.diagnostics(),'events':s.active_events(),'observation':obs}
  self.events.update(row['events']);self.rows.append(row)
  with (self.directory/'observations.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
  return row
 def advance(self,target):
  s=self.session;steps=round((target-s.get_simulation_time())/.02)
  if steps<0:raise RuntimeError('TIME_REVERSAL')
  for _ in range(steps):
   if not s._native.advance_step():raise RuntimeError('NATIVE_ADVANCE_FAILED')
   now=s.get_simulation_time();ev=s.active_events();names=set(ev);self.events.update(names)
   if names!=self.last_events:
    with (self.directory/'native_events.jsonl').open('a') as f:f.write(json.dumps({'time_s':now,'events':ev})+'\n')
    self.last_events=names
   if names & HALT_EVENTS:raise RuntimeError('NATIVE_CRITICAL_EVENT:'+','.join(sorted(names & HALT_EVENTS)))
   if abs(now-round(now))<1e-6:self.capture()
 def submit(self,payload,phase):
  rec={'time_s':self.session.get_simulation_time(),'phase':phase,'payload':payload,'state':'SUBMITTING'};self.actions.append(rec);dump(self.directory/'actions.json',self.actions)
  try:rec['native_result']=self.session._submit(payload,phase);rec['state']='ACCEPTED'
  except Exception as e:rec.update(state='UNKNOWN',error=str(e));raise
  finally:dump(self.directory/'actions.json',self.actions)
 def prepare(self):
  components=self.pattern['component_injuries'];conditions=[c for c in components if c['injury_type']=='dehydration'];config=PatientInitializer().configuration({'patient_id':self.pid,'injuries':conditions}) if conditions else None
  dump(self.directory/'patient_configuration.json',config);self.session.initialize(self.directory/'pulse.log',config)
  (self.directory/'initial_state.json').write_text(self.session.serialize_state());self.capture();self.advance(60);(self.directory/'preinjury_state.json').write_text(self.session.serialize_state())
  dyn=[c for c in components if c['injury_type'] not in ('dehydration','carbon_monoxide_exposure','environmental_hypoxia')]
  onsets=self.pattern['simulation_timeline'].get('component_onsets_s',{})
  for c in sorted(CasualtyInput(patient_id=self.pid,injuries=dyn).injuries,key=lambda c:onsets.get(c.injury_type,60)):
   self.advance(onsets.get(c.injury_type,60));self.submit(InjuryAdapter().convert_dynamic(c),'injury')
  env=self.pattern['environment_profile']
  if env:self.submit(environment_action(env['co'],env['oxygen']),'environment')
  self.advance(self.pattern['simulation_timeline']['decision_s']);(self.directory/'decision_state.json').write_text(self.session.serialize_state());return self.rows[-1]
 def finish(self):
  self.advance(self.pattern['simulation_timeline']['end_s']);return self.rows[-1]
 def close(self):
  if self.session.ready:(self.directory/'final_state.json').write_text(self.session.serialize_state())
  self.session.close()