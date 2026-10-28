"""Offline evidence and adverse mutations; these tests never start Pulse."""
import copy,json
import pytest
from core301.paths import PROJECT_ROOT
from core301.runtime.v2_1.registry import patterns
from core301.runtime.v2_1.risk_gate_v2 import assess, event_match
from core301.runtime.v2.errors import V2Error
O=PROJECT_ROOT/'research_artifacts/v2_1_battle_composite_injuries_v0.1'
def inputs(i):
 d=O/'experiments/raw/runtime_final'/str(i)
 read=lambda p:[json.loads(s) for s in p.read_text().splitlines()]
 return [i,patterns()[i],read(d/'native/observations.jsonl'),read(d/'native/native_events.jsonl'),(d/'native/pulse.log').read_text(),json.loads((d/'accepted_endpoint_state.json').read_text())]
@pytest.mark.parametrize('i',range(5))
def test_real_saved_risk_evidence(i):
 r=assess(*inputs(i));assert r['passed'],r
 assert not r['production_enabled'] and not r['automatic_admission']
@pytest.mark.parametrize('i',range(5))
def test_critical_event_never_waived(i):
 a=inputs(i);a[3][-1]['events']['BrainOxygenDeficit']=.02
 r=assess(*a);assert not r['passed'] and r['critical_veto']
@pytest.mark.parametrize('mutation',['extended','missing_transition','terminal','worse_RR','missing_RR','nan_RR'])
def test_tachypnea_scope(mutation):
 a=inputs(2)
 if mutation=='extended':
  r=next(r for r in a[3] if abs(r['time_s']-309)<1e-6);r['time_s']+=.02
 elif mutation=='missing_transition':a[3].pop(1)
 elif mutation=='terminal':a[2][-1]['events']['Tachypnea']=300
 else:
  r=next(r for r in a[2] if abs(r['time_s']-200)<1e-6)
  if mutation=='worse_RR':r['values']['vitals.respiration_rate']+=1
  elif mutation=='missing_RR':del r['values']['vitals.respiration_rate']
  else:r['values']['vitals.respiration_rate']=float('nan')
 assert not assess(*a)['passed']
@pytest.mark.parametrize('i,key',[(3,'laboratory.blood_ph'),(3,'laboratory.arterial_carbon_dioxide_pressure'),(4,'aorta_sodium_mEq_L')])
def test_adverse_value_outside_approved_trace(i,key):
 a=inputs(i);group='diagnostics' if i==4 else 'values';a[2][-1][group][key]+=.01
 assert not assess(*a)['passed']
@pytest.mark.parametrize('mutation',['larger_negative','missing_stop','still_active','old_timeline'])
def test_thoracic_numeric_scope(mutation):
 a=inputs(0)
 if mutation=='larger_negative':a[2][-1]['diagnostics']['residual_blood_volume_mL']=-.1
 elif mutation=='missing_stop':a[4]=''
 elif mutation=='still_active':a[5]['ActiveActions']['AnyAction'].append({'PatientAction':{'TubeThoracostomy':{}}})
 else:
  a[1]['simulation_timeline']['decision_s']=180
  with pytest.raises(V2Error,match='exact fixed'):assess(*a)
  return
 assert not assess(*a)['passed']
def test_approval_evidence_integrity(tmp_path,monkeypatch):
 from core301.runtime.v2_1 import risk_gate_v2 as gate
 p=tmp_path/'changed.json';p.write_text('{}');monkeypatch.setattr(gate,'MANIFEST',p)
 with pytest.raises(V2Error,match='missing or changed'):assess(*inputs(4))
@pytest.mark.parametrize('i',range(5))
def test_candidate_evaluator_on_saved_native_case(tmp_path,i):
 """Offline evaluator integration only; never claimed as a fresh native E2E."""
 from types import SimpleNamespace
 from core301.runtime.v2_1.acceptance_v2 import evaluate
 a=inputs(i);d=tmp_path/'native';d.mkdir()
 (d/'native_events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in a[3]))
 (d/'pulse.log').write_text(a[4])
 case=SimpleNamespace(_live=lambda:None,_guard=lambda:None,pattern=a[1],index=i,directory=tmp_path,
  _time=lambda:a[1]['simulation_timeline']['end_s'],_engine=SimpleNamespace(rows=a[2],session=SimpleNamespace(serialize_state=lambda:json.dumps(a[5]))),
  _controlled={'hemothorax'},journal={'requests':{'joint':{'state':'COMPLETED','plan':{'bundle':'AB'}}}},validation_only=True)
 r=evaluate(case)
 assert r['engineering_case_passed'] and r['formal_admission']=='NOT_GRANTED_BY_CASE_RESULT'
 assert r['clinical_safety']=='NOT_EVALUATED' and not r['production_enabled']
 case.journal['requests']['joint']['state']='UNKNOWN'
 assert not evaluate(case)['engineering_case_passed']
