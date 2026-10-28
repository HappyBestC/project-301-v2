import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from core301.paths import PROJECT_ROOT
from core301.runtime.v2_1 import open_research_composite_case
from core301.runtime.v2_1.registry import patterns
from core301.runtime.v2_1.resources import study_resources,Resources
from core301.runtime.v2_1.contracts import CompositePlan
from core301.runtime.v2.errors import V2Error
from core301.pulse.observation_projector import Sample
from core301.runtime.v2.exposure_validation import PUBLIC_FIELDS
from core301.runtime.v2_1.acceptance import repeat_check
O=PROJECT_ROOT/'research_artifacts/v2_1_battle_composite_injuries_v0.1'
def open_case(tmp_path,i=2,**kw):
 return open_research_composite_case(patterns()[i]['pattern_id'],patient_id='p',run_id='r',directory=tmp_path,mode='research',validation_only=True,observation_access=True,resources=study_resources('r','p'),**kw)
@pytest.mark.parametrize('i',range(5))
def test_formal_gate_matches_verified_registry(tmp_path,i):
 from core301.runtime.v2_1.admission import ADMITTED
 if patterns()[i]["pattern_id"] in ADMITTED:
  c=open_research_composite_case(patterns()[i]["pattern_id"],patient_id="p",run_id="r",directory=tmp_path/"case",mode="research")
  assert c.validation_only is False and c._engine is None
  c.close();return
 with pytest.raises(V2Error,match='Composite evidence'):
  open_research_composite_case(patterns()[i]['pattern_id'],patient_id='p',run_id='r',directory=tmp_path/'case',mode='research')
 assert not (tmp_path/'case').exists()
@pytest.mark.parametrize('i',range(5))
def test_production_denied(tmp_path,i):
 with pytest.raises(V2Error) as e:open_research_composite_case(patterns()[i]['pattern_id'],patient_id='p',run_id='r',directory=tmp_path/'case')
 assert e.value.code=='PRODUCTION_NOT_ENABLED'
def test_unknown_pattern(tmp_path):
 with pytest.raises(V2Error):open_research_composite_case('made_up',patient_id='p',run_id='r',directory=tmp_path,mode='research',validation_only=True)
@pytest.mark.parametrize('field',['severity','side','native_payload','production_enabled','approval'])
def test_plan_no_native_override(field):
 with pytest.raises(ValueError):CompositePlan(patient_id='p',pattern_id='a',bundle='AB',**{field:True})
def test_lock_and_restart(tmp_path):
 c=open_case(tmp_path/'case')
 with pytest.raises(V2Error) as e:open_case(tmp_path/'case')
 assert e.value.code=='SESSION_IN_USE'
 c.close();c=open_case(tmp_path/'case')
 with pytest.raises(V2Error):c.prepare()
 c.close()
@pytest.mark.parametrize('change',['patient','stock','holds','permission','route'])
def test_resource_preflight(change):
 g=study_resources('r','p')
 if change=='patient':g.patient_id='other'
 if change=='stock':g.stock['saline_500ml_bag']=0
 if change=='holds':g.holds['medic']=0
 if change=='permission':g.permissions=frozenset()
 if change=='route':g.protected_route_available=False
 with pytest.raises(V2Error):Resources(g,'r','p').reserve(['remove_from_exposure','fluid_resuscitation'])
def test_reservation_once_and_consumption():
 r=Resources(study_resources('r','p'),'r','p');r.reserve(['intubation','mechanical_ventilation']);r.begin('intubation')
 assert r.grant.stock['airway_kit']==0
 with pytest.raises(V2Error):r.reserve(['intubation'])
@pytest.mark.parametrize('i',range(5))
@pytest.mark.parametrize('treated',[False,True])
def test_native_saved_source_and_devices(tmp_path,i,treated):
 root=O/'experiments/raw'
 d=root/'thoracic_timing_v2/AB' if i==0 else root/'stage2'/str(i)/'AB'
 state=json.loads((d/('post_actions_state.json' if treated else 'decision_state.json')).read_text())
 c=open_case(tmp_path/f'{i}-{treated}',i)
 t=state['SimulationTime']['ScalarTime']['Value'];fields={k:Sample(1,t) for k in PUBLIC_FIELDS}
 class SavedSession:
  def serialize_state(self):return json.dumps(state)
  def read_requested_data(self):return fields
  def diagnostics(self):
   from core301.runtime.v2_1.native_backend import COMMON
   return {k:140 if k=='aorta_sodium_mEq_L' else 1 for k,_ in COMMON}
  def active_events(self):return {}
  def get_simulation_time(self):return t
 c._engine=SimpleNamespace(session=SavedSession());c._condition_signature=state.get('Conditions',{})
 if treated:
  c._executed=[a for b in ['A','B'] for a in c.pattern['treatment_bundles'][b]]
  c._controlled={x['injury_type'] for x in c.pattern['component_injuries'] if 'hemorrhage' in x['injury_type'] or x['injury_type']=='hemothorax'}
  c._removed=i in (3,4)
 try:
  c._guard()
  saved_diagnostics=c._engine.session.diagnostics
  c._engine.session.diagnostics=lambda:{'aorta_sodium_mEq_L':140}
  with pytest.raises(V2Error) as e:c._guard()
  assert e.value.code=='MISSING_OBSERVATION'
  c._engine.session.diagnostics=saved_diagnostics
  state.setdefault('ActiveActions',{}).setdefault('AnyAction',[]).append({'PatientAction':{'Bronchoconstriction':{'Severity':{'Scalar0To1':{'Value':.4}}}}})
  with pytest.raises(V2Error) as e:c._guard()
  assert e.value.code=='UNREGISTERED_NATIVE_SOURCE'
 finally:c._engine=None;c.close()
def test_repeat_missing_or_changed_data():
 row={'time_s':0,'values':{'x':1.},'diagnostics':{'Na':140.},'events':{}}
 assert repeat_check([row],[row],0)['passed']
 other=copy.deepcopy(row);other['values']['x']=2
 assert not repeat_check([row],[other],0)['passed']
 assert not repeat_check([row],[row],1)['passed']
def test_restart_unknown_query(tmp_path):
 c=open_case(tmp_path/'case');c.journal['requests']['id']={'state':'SUBMITTING'};c._flush();c.close()
 c=open_case(tmp_path/'case');assert c.query('id')['state']=='UNKNOWN';c.close()

def test_close_preserves_completed_receipt(tmp_path):
 c=open_case(tmp_path/'case');c.resources.reserve(['intubation','mechanical_ventilation']);c.resources.begin('intubation')
 c.journal['requests']['done']={'state':'COMPLETED','resources':c.resources.record,'actions':[{'state':'NATIVE_ACCEPTED'}]};c._flush()
 before=c.query('done');c.close();assert c.query('done')==before
 reopened=open_case(tmp_path/'case');assert reopened.query('done')==before;reopened.close()

def test_uncertain_submission_is_quarantined_and_idempotent(tmp_path):
 c=open_case(tmp_path/'case');c._prepared=True;c._time=lambda:180;c._guard=lambda:None;c._contexts['ctx']=180
 calls=[]
 def uncertain(*args):calls.append(args);raise RuntimeError('Lost native acknowledgement')
 c._engine=SimpleNamespace(submit=uncertain)
 plan={'patient_id':'p','pattern_id':c.pattern['pattern_id'],'bundle':'AB'}
 try:
  with pytest.raises(RuntimeError,match='Lost native'):c.execute(plan,request_id='id',context_ref='ctx')
  assert c.query('id')['state']=='UNKNOWN'
  assert c.execute(plan,request_id='id',context_ref='ctx')['state']=='UNKNOWN'
  assert len(calls)==1
  with pytest.raises(V2Error) as e:c.execute(plan,request_id='new',context_ref='ctx')
  assert e.value.code=='EXECUTION_HALTED'
 finally:c._engine=None;c.close()

def test_foreign_directory_not_overwritten(tmp_path):
 p=tmp_path/'case';p.mkdir();(p/'foreign.txt').write_text('preserve')
 with pytest.raises(V2Error) as e:open_case(p)
 assert e.value.code=='FOREIGN_DIRECTORY' and (p/'foreign.txt').read_text()=='preserve'

def test_missing_observation_access_fails_before_engine(tmp_path):
 p=patterns()[1]['pattern_id'];c=open_research_composite_case(p,patient_id='p',run_id='r',directory=tmp_path/'case',mode='research',validation_only=True)
 with pytest.raises(V2Error) as e:c.prepare()
 assert e.value.code=='OBSERVATION_NOT_AUTHORIZED' and c._engine is None;c.close()

def test_modified_profile_cannot_load(monkeypatch,tmp_path):
 from core301.runtime.v2_1 import registry
 f=tmp_path/'modified.yaml';f.write_text('{}');monkeypatch.setattr(registry,'CONFIG',f)
 with pytest.raises(V2Error) as e:registry.patterns()
 assert e.value.code=='PROFILE_TAMPERED'

def test_modified_reference_cannot_pass(monkeypatch,tmp_path):
 from core301.runtime.v2_1 import acceptance
 fake=tmp_path/'fake.jsonl';fake.write_text('{}\n')
 monkeypatch.setattr(acceptance,'REFERENCES',{1:{'treated':{'path':str(fake),'sha256':'0'*64}}})
 with pytest.raises(V2Error) as e:acceptance.reference(1,'treated')
 assert e.value.code=='EVIDENCE_INVALID'

@pytest.mark.parametrize('field',['patient_id','run_id','index','validation_only','timeline'])
def test_binding_mutation_fails_before_initialization(tmp_path,field):
 c=open_case(tmp_path/'case')
 if field=='timeline':c.pattern['simulation_timeline']['end_s']=9999
 else:setattr(c,field,'tampered')
 try:
  with pytest.raises(V2Error) as e:c.prepare()
  assert e.value.code=='PROFILE_OR_IDENTITY_CHANGED' and c._engine is None
 finally:c.close()

@pytest.mark.parametrize('i',range(5))
def test_final_native_trajectory_meets_extended_read_guards(i):
 from core301.runtime.v2_1.native_backend import COMMON
 p=O/'experiments/raw/runtime_final'/str(i)/'native/observations.jsonl'
 for line in p.read_text().splitlines():
  r=json.loads(line)
  assert all(r['diagnostics'].get(k) is not None for k,_ in COMMON)
  for group in ('vitals','circulation','respiratory','laboratory'):
   assert all(m['status']=='available' and m['observed_at_s']==r['time_s'] for m in r['observation'][group].values())

@pytest.mark.parametrize('bundle',['A','B','BA'])
def test_formal_rejects_unadmitted_bundles(monkeypatch,tmp_path,bundle):
 from core301.runtime.v2_1 import runtime
 monkeypatch.setattr(runtime,'verify_admission',lambda pattern_id:'test_gate_only')
 p=patterns()[1]['pattern_id'];c=runtime.open_research_composite_case(p,patient_id='p',run_id='r',directory=tmp_path/'case',mode='research',observation_access=True,resources=study_resources('r','p'))
 c._prepared=True;c._time=lambda:180;c._guard=lambda:None;c._contexts['ctx']=180
 try:
  with pytest.raises(V2Error) as e:c.execute({'patient_id':'p','pattern_id':p,'bundle':bundle},request_id='id',context_ref='ctx')
  assert e.value.code=='BUNDLE_NOT_ADMITTED' and not c.journal['requests']
 finally:c.close()

def test_admission_manifest_tamper_fails(monkeypatch,tmp_path):
 from core301.runtime.v2_1 import admission
 p=tmp_path/'bad.json';p.write_text('{}');monkeypatch.setattr(admission,'MANIFEST',p)
 with pytest.raises(V2Error) as e:admission.verify_admission(patterns()[1]['pattern_id'])
 assert e.value.code=='ADMISSION_EVIDENCE_INVALID'

@pytest.mark.parametrize('failure',['missing','changed'])
def test_admission_proof_integrity(monkeypatch,tmp_path,failure):
 import hashlib
 from core301.runtime.v2_1 import admission
 record=json.loads(admission.MANIFEST.read_text());proof=tmp_path/'proof'
 if failure=='changed':proof.write_text('changed')
 record['proof_sha256']={str(proof):'0'*64};manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(record))
 monkeypatch.setattr(admission,'MANIFEST',manifest);monkeypatch.setattr(admission,'MANIFEST_SHA256',hashlib.sha256(manifest.read_bytes()).hexdigest())
 with pytest.raises(V2Error) as e:admission.verify_admission(patterns()[1]['pattern_id'])
 assert e.value.code=='ADMISSION_EVIDENCE_INVALID'
