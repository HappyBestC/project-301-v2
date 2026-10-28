import copy
import pytest
from core301.pulse.v2.hemothorax_endpoint_review import FIXED,review_endpoints

def samples():
    out=[]
    for t,v,source,tube in [(660.,27.,True,False),(661.,26.,False,True),(716.,-.003,False,False),(960.,-.003,False,False)]:
        out.append(dict(patient_id='P',side='Left',simulation_time_s=t,session_epoch='E',
          residual_blood_volume_mL={'value':v,'status':'available','observed_at_s':t},
          source_flow_mL_s={'value':None,'status':'unavailable','observed_at_s':t},source_action_active=source,tube_action_active=tube,tube_flow_mL_min=30. if tube else None,
          events=[{'native_time_s':715.56,'raw_log_line':'Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.'}] if t>715.56 else [],
          numeric_interpretation='negative_native_raw' if v<0 else 'native_raw'))
    return out

def review(s,**kw):return review_endpoints(s,configuration=kw.get('configuration',FIXED),safety_events=kw.get('safety_events',{}),physiology_complete=kw.get('physiology_complete',True))

def test_longitudinal_raw_preserved_and_unapproved():
    s=samples();before=copy.deepcopy(s);r=review(s,safety_events={'Hypernatremia':1.})
    assert r['n1_consistent'] and r['local_control_supported'] and not r['goal_passed'] and r['normalized_volume_mL'] is None
    assert r['safety_disposition']=='UNRESOLVED_EVENTS' and s==before

@pytest.mark.parametrize('change,expected',[
 ('initial_source','PRETREATMENT_SOURCE_NOT_CONFIRMED'),('epoch','IDENTITY_OR_EPOCH_MISMATCH'),('order','NONMONOTONIC_TIME'),('window','INCOMPLETE_FIXED_WINDOW'),
 ('active','ACTIVE_TUBE_EVIDENCE_MISSING_OR_CONFLICTING'),('event','NO_NATIVE_AUTO_STOP'),('drift','POST_STOP_ACTIVITY_OR_VOLUME_DRIFT'),
 ('source','SOURCE_OR_TUBE_STILL_ACTIVE'),('range','NEGATIVE_OUTSIDE_SINGLE_TICK')])
def test_reject_dangerous_evidence(change,expected):
    s=samples()
    if change=='initial_source':s[0]['source_action_active']=False
    elif change=='epoch':s[-1]['session_epoch']='OTHER'
    elif change=='order':s.reverse()
    elif change=='window':s=s[:-1]
    elif change=='active':s[1]['tube_flow_mL_min']=60.
    elif change=='event':
        for o in s:o['events']=[]
    elif change=='drift':s[-1]['residual_blood_volume_mL']['value']=-.004
    elif change=='source':s[-1]['source_action_active']=True
    elif change=='range':
        for o in s[2:]:o['residual_blood_volume_mL']['value']=-.011
    r=review(s);assert expected in r['problems'] and not r['local_control_supported'] and not r['goal_passed']

def test_missing_systemic_does_not_grant_success():
    r=review(samples(),physiology_complete=False)
    assert 'MISSING_SYSTEMIC_OBSERVATION' in r['problems'] and not r['goal_passed']

def test_configuration_exact_scope():
    config=dict(FIXED,dt_s=.04);r=review(samples(),configuration=config)
    assert 'CONFIGURATION_OUT_OF_SCOPE' in r['problems'] and not r['n1_consistent']
