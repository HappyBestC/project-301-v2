"""Boundary tests for interpretation/risk, not substitutes for native E2E."""
import copy,json
import pytest
from core301.pulse.v2.hemothorax_acceptance import review_fixed_endpoints,FIXED
from core301.runtime.v2.restricted_risk import reference,conformance,verify_risk_scope,FILES

def samples():
    rows=[]
    for t in [660.,660.04,*map(float,range(661,961))]:
        tube=660<t<716;v=27. if t==660 else 26. if tube else -.003
        rows.append(dict(patient_id='P',side='Left',simulation_time_s=t,session_epoch='E',
            residual_blood_volume_mL={'value':v,'status':'available','observed_at_s':t},
            source_flow_mL_s={'value':None,'status':'unavailable','observed_at_s':t},source_action_active=t==660,tube_action_active=tube,
            numeric_interpretation='negative_native_raw' if v<0 else 'native_raw',tube_flow_mL_min=30. if tube else None,events=[{'native_time_s':715.56,'raw_log_line':'Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.'}] if t>=716 else []))
    return rows

def review(s,**kw):return review_fixed_endpoints(s,configuration=kw.get('configuration',FIXED),safety_events={'Hypernatremia':1.},physiology_complete=kw.get('physiology_complete',True))

def test_final_rule_preserves_raw_and_separates_safety():
    s=samples();before=copy.deepcopy(s);r=review(s)
    assert r['local_control_supported'] and r['n1_consistent'] and not r['goal_passed']
    assert r['normalized_volume_mL'] is None and s==before and r['safety_events']=={'Hypernatremia':1.}

@pytest.mark.parametrize('case',['side','missing_second','missing_early_tube','overshoot','drift','source','flow','auto_stop','missing_phys','wrong_dt','wrong_order'])
def test_final_rule_rejects(case):
    s=samples();kw={}
    if case=='side':
        for x in s:x['side']='Right'
    elif case=='missing_second':s.pop(70)
    elif case=='missing_early_tube':s=s[:1]+s[3:]
    elif case=='overshoot':s[2]['residual_blood_volume_mL']['value']=-.011
    elif case=='drift':s[-1]['residual_blood_volume_mL']['value']=-.004
    elif case=='source':s[-1]['source_action_active']=True
    elif case=='flow':s[1]['tube_flow_mL_min']=31.
    elif case=='auto_stop':
        for x in s:x['events']=[]
    elif case=='missing_phys':kw['physiology_complete']=False
    elif case=='wrong_dt':kw['configuration']=dict(FIXED,dt_s=.04)
    else:s.reverse()
    assert not review(s,**kw)['local_control_supported']

@pytest.mark.parametrize('value,expected',[(-.01,True),(-.01000001,False),(0.,True),(.001,False)])
def test_numeric_boundary_is_tick_quantity(value,expected):
    s=samples()
    for x in s:
        if x['simulation_time_s']>=716:
            x['residual_blood_volume_mL']['value']=value;x['numeric_interpretation']='negative_native_raw' if value<0 else 'native_raw'
    assert review(s)['local_control_supported']==expected

def test_risk_requires_pinned_user_record():
    assert verify_risk_scope()['clinical_safety_certification'] is False

@pytest.mark.parametrize('kind',['hemothorax','carbon_monoxide_exposure'])
def test_risk_requires_full_verified_trajectory(kind):
    assert not conformance(kind,[])['passed']
    r=reference(kind);samples=[{'time_s':float(t),'values':v} for t,v in r.items()]
    assert conformance(kind,[],samples)['passed']
    samples[-1]['values']['Na']+=.001
    result=conformance(kind,[],samples)
    assert not result['passed'] and result['failures'][-1]['reason']=='outside_verified_trajectory'

def test_modified_evidence_denied(tmp_path,monkeypatch):
    import core301.runtime.v2.restricted_risk as risk
    p=tmp_path/'altered.json';p.write_text('{}')
    refs=dict(FILES);refs['approval']={'path':str(p),'sha256':FILES['approval']['sha256']}
    monkeypatch.setattr(risk,'FILES',refs)
    with pytest.raises(Exception,match='Pinned risk'):verify_risk_scope()

def test_no_risk_reference_for_hypoxia():
    from core301.runtime.v2.errors import V2Error
    with pytest.raises(V2Error) as e:reference('environmental_hypoxia')
    assert e.value.code=='RISK_SCOPE_NOT_AUTHORIZED'
