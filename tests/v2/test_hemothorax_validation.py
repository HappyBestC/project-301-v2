"""Contract/resource/denial tests; these do not stand in for native physiology."""
import pytest
from pydantic import ValidationError
from core301.contracts.v2.hemothorax_observation import HemothoraxObservation
from core301.contracts.v2.treatment import TreatmentPlan
from core301.runtime.v2.hemothorax_resources import validation_resources
from core301.runtime.v2.hemothorax_validation import HemothoraxValidationRuntime
from core301.runtime.v2.errors import V2Error
from core301.pulse.v2.hemothorax_numeric_review import review_overshoot
from core301.pulse.v2.protocol_book import OPEN_INJURIES, RESERVED_ACTIONS

def observation(v):
    return dict(patient_id='P',side='Left',simulation_time_s=716.,session_epoch='test',
        residual_blood_volume_mL={'value':v,'status':'available' if v is not None else 'unavailable','observed_at_s':716.},
        source_flow_mL_s={'value':None,'status':'unavailable','observed_at_s':716.},source_action_active=False,tube_action_active=False,tube_flow_mL_min=None,events=[],
        numeric_interpretation='unavailable' if v is None else 'negative_native_raw' if v<0 else 'native_raw')

@pytest.mark.parametrize('value',[-.003148148,-.01,-.01000001,-1.,0.,27.776852,None])
def test_raw_preserved_no_admission(value):
    obj=HemothoraxObservation(**observation(value))
    assert obj.residual_blood_volume_mL.value==value and obj.source_flow_mL_s.value is None
    assert obj.clinical_efficacy=='NOT_EVALUATED' and obj.admission=='PENDING_RESEARCH_RULE_APPROVAL'

@pytest.mark.parametrize('field,value',[('admission','APPROVED'),('clinical_efficacy','PASSED'),('side','Right'),('numeric_interpretation','native_raw'),('residual_blood_volume_mL',{'value':float('nan'),'status':'available','observed_at_s':716.})])
def test_observation_cannot_forge_status(field,value):
    d=observation(-.003);d[field]=value
    with pytest.raises(ValidationError):HemothoraxObservation(**d)

@pytest.mark.parametrize('value,expected',[(-.003148148,True),(-.01,True),(-.010000001,False),(-1.,False),(None,False),(0.,False)])
def test_dimensional_boundary_is_not_a_pass(value,expected):
    r=review_overshoot(value,dt_s=.02,flow_mL_min=30,source_active=False,tube_active=False,auto_stop_seen=True)
    assert r['consistent_with_single_step_overshoot']==expected
    assert r['raw_volume_mL']==value and r['normalized_volume_mL'] is None and not r['efficacy_passed']

@pytest.mark.parametrize('overrides',[{'dt_s':.01},{'flow_mL_min':60},{'source_active':True},{'tube_active':True},{'auto_stop_seen':False},{'previous_stopped_volume':-.002}])
def test_missing_or_wrong_evidence_not_explained(overrides):
    kw=dict(dt_s=.02,flow_mL_min=30,source_active=False,tube_active=False,auto_stop_seen=True);kw.update(overrides)
    assert not review_overshoot(-.003,**kw)['consistent_with_single_step_overshoot']

def plan():return TreatmentPlan.model_validate({'patient_id':'P','actions':[{'action_type':'control_hemothorax_bleeding','side':'Left'},{'action_type':'chest_tube','side':'Left'}]})

def test_resources_whole_plan_one_kit_and_replay():
    r=validation_resources('R','P');p=plan();assert r.snapshot('R','P').chest_tube_kit==1
    r.reserve('x',p,'R','P');assert r.snapshot('R','P').chest_tube_kit==0
    r.begin('x','a','control_hemothorax_bleeding');r.acknowledge('x','a',True)
    r.begin('x','b','chest_tube');r.acknowledge('x','b',None)
    assert r.stock['chest_tube_kit']==0 and r.audit()['reservations']['x']['begun']['b']['submission_status']=='quarantined'
    with pytest.raises(V2Error):r.begin('x','b','chest_tube')
    r.release_unused('x');assert r.stock['chest_tube_kit']==0

@pytest.mark.parametrize('kind',['stock','permission','capability','identity'])
def test_resources_reject_before_any_reservation(kind):
    r=validation_resources('R','P')
    if kind=='stock':r.stock['chest_tube_kit']=0
    if kind=='permission':r.permissions=frozenset()
    if kind=='capability':r.capabilities=frozenset()
    before=r.audit()
    with pytest.raises(V2Error):r.reserve('x',plan(),'other' if kind=='identity' else 'R','P')
    assert r.audit()==before

@pytest.mark.parametrize('change',[{'side':'Right'},{'severity':.6},{'injury_type':'external_hemorrhage','compartment':'RightLeg'}])
def test_bad_injury_denied_without_native_initialize(tmp_path,change):
    rt=HemothoraxValidationRuntime('P',tmp_path,run_id='R',mode='research',validation_only=True)
    injury={'injury_type':'hemothorax','side':'Left','severity':.8};injury.update(change)
    with pytest.raises(V2Error):rt.prepare({'patient_id':'P','injuries':[injury]})
    assert not rt.session.ready and not rt.session.action_results
    assert rt.journal.data['events'][-1]['state']=='REJECTED'
    rt.close()

def test_no_admission_or_production_flag(tmp_path):
    with pytest.raises(V2Error):HemothoraxValidationRuntime('P',tmp_path,run_id='R',mode='research')
    with pytest.raises(V2Error):HemothoraxValidationRuntime('P',tmp_path,run_id='R',validation_only=True)
    assert len(OPEN_INJURIES)==7 and 'hemothorax' not in OPEN_INJURIES and 'chest_tube' in RESERVED_ACTIONS
