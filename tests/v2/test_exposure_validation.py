import json
import pytest
from pydantic import ValidationError
from core301.contracts.v2.exposure_validation import ExposureInput,EvacuationPlan,EvacuationResources,ExposureObservation
from core301.pulse.v2.exposure_session import environment_action,environment_signature,PROFILES
from core301.runtime.v2.exposure_validation import ExposureValidationRuntime,safety_review,HALT_EVENTS
from core301.runtime.v2.errors import V2Error

def diagnostic(**changes):
    x=dict(patient_id='P',exposure_id='E',session_epoch='epoch',simulation_time_s=10.0,native_events={'Hypernatremia':1.0})
    for name in ('aorta_co_saturation','aorta_cohb_g_dL','oxygen_saturation','aorta_sodium_mEq_L','ambient_co_fraction','ambient_oxygen_fraction'):
        x[name]={'value':.2,'status':'available','observed_at_s':10.0}
    x.update(changes);return x

def fixture_resource(run='R'):
    return dict(run_id=run,patient_id='P',evacuation_teams=1,protected_route_available=True,receiving_environment_verified=True,permission='research_environment_removal')

@pytest.mark.parametrize('field,value',[('admission','ADMITTED'),('clinical_efficacy','PASSED'),('simulation_time_s',-1.),('session_epoch',''),('patient_id',' ')])
def test_no_forged_admission_or_identity(field,value):
    with pytest.raises(ValidationError):ExposureObservation.model_validate(diagnostic(**{field:value}))

@pytest.mark.parametrize('value',[-.1,1.1,float('nan'),float('inf')])
def test_no_bad_saturation(value):
    x=diagnostic();x['aorta_co_saturation']['value']=value
    with pytest.raises(ValidationError):ExposureObservation.model_validate(x)

@pytest.mark.parametrize('changes',[{'observed_at_s':9.0},{'observed_at_s':11.0},{'status':'unavailable'},{'value':None}])
def test_missing_or_stale_measurement_consistency(changes):
    x=diagnostic();x['oxygen_saturation'].update(changes)
    with pytest.raises(ValidationError):ExposureObservation.model_validate(x)

def test_unavailable_stays_null_and_cannot_pass():
    x=diagnostic();x['aorta_co_saturation'].update(value=None,status='unavailable')
    obs=ExposureObservation.model_validate(x);review=safety_review(obs)
    assert obs.aorta_co_saturation.value is None and review['goal_passed'] is False
    assert review['native_events']=={'Hypernatremia':1.0} and review['safety_disposition']=='UNRESOLVED_EVENTS'

@pytest.mark.parametrize('events',[{}, {'Hypernatremia':1.0},{'Hypoxia':30.0},{'IrreversibleState':0.0},{'CardiacArrest':0.0},{'CardiovascularCollapse':0.0},{'CriticalBrainOxygenDeficit':0.0},{'HypovolemicShock':0.0}])
def test_no_event_waiver_or_auto_admission(events):
    review=safety_review(ExposureObservation.model_validate(diagnostic(native_events=events)))
    assert review['admission']=='PENDING_RESEARCH_RULE_APPROVAL' and not review['goal_passed']
    assert review['native_events']==events and review['halt_required']==bool(HALT_EVENTS.intersection(events))

@pytest.mark.parametrize('extra',[{'oxygen_flow':1.0},{'severity':.5},{'native_payload':{}},{'action_type':'supplemental_oxygen'},{'protocol':'approved'}])
def test_plan_has_no_free_parameters(extra):
    with pytest.raises(ValidationError):EvacuationPlan.model_validate(dict(patient_id='P',exposure_id='E',**extra))

@pytest.mark.parametrize('extra',[{'severity':.5},{'co_fraction':.01},{'exposure_type':'cold_stress'},{'profile_version':'production'}])
def test_input_fixed_scope(extra):
    x=dict(patient_id='P',exposure_id='E',exposure_type='carbon_monoxide_exposure');x.update(extra)
    with pytest.raises(ValidationError):ExposureInput.model_validate(x)

def test_environment_action_has_physical_gas_balance():
    for co,o2,*_ in PROFILES.values():
        gases=environment_action(co,o2)['EnvironmentAction']['ChangeEnvironmentalConditions']['EnvironmentalConditions']['AmbientGas']
        assert sum(x['Amount']['Scalar0To1']['Value'] for x in gases)==pytest.approx(1)
    assert 'PatientAction' not in environment_action(0,.21)

def test_signature_normalizes_native_zero_and_order():
    c=environment_action(0,.21)['EnvironmentAction']['ChangeEnvironmentalConditions']['EnvironmentalConditions']
    c['AmbientGas'][-1]['Amount']['Scalar0To1']={}
    state={'Environment':{'Common':{'EnvironmentalConditions':c}}}
    one=environment_signature(state);c['AmbientGas'].reverse();assert one==environment_signature(state)
    assert one['AmbientGas']['CarbonMonoxide']==0

@pytest.mark.parametrize('args,code',[({},'PRODUCTION_NOT_ENABLED'),({'mode':'research'},'RESEARCH_RULE_APPROVAL_PENDING')])
def test_default_disabled_before_files(tmp_path,args,code):
    with pytest.raises(V2Error) as e:ExposureValidationRuntime(patient_id='P',run_id='R',directory=tmp_path/'never',**args)
    assert e.value.code==code and not (tmp_path/'never').exists()

def test_resource_identity_before_creation(tmp_path):
    with pytest.raises(V2Error,match='another run'):ExposureValidationRuntime(patient_id='P',run_id='R',directory=tmp_path/'never',mode='research',validation_only=True,resources=fixture_resource('WRONG'))
    assert not (tmp_path/'never').exists()

def test_lock_reopen_and_restore_denial(tmp_path):
    kw=dict(patient_id='P',run_id='R',directory=tmp_path/'run',mode='research',validation_only=True)
    r=ExposureValidationRuntime(**kw)
    with pytest.raises(V2Error) as exc:ExposureValidationRuntime(**kw)
    assert exc.value.code=='SESSION_IN_USE'
    with pytest.raises(V2Error) as exc:r.restore_state('{}')
    assert exc.value.code=='UNSUPPORTED_RECOVERY'
    r.close();r2=ExposureValidationRuntime(**kw)
    with pytest.raises(V2Error) as exc:r2.prepare(dict(patient_id='P',exposure_id='E',exposure_type='carbon_monoxide_exposure'))
    assert exc.value.code=='RESTART_REQUIRES_RECOVERY' and r2._session._native._engine is None
    r2.close()

def test_other_journal_not_modified(tmp_path):
    path=tmp_path/'execution_journal.json';path.write_text('{"exposure_profile":"other"}')
    with pytest.raises(V2Error) as exc:ExposureValidationRuntime(patient_id='P',run_id='R',directory=tmp_path,mode='research',validation_only=True)
    assert exc.value.code=='JOURNAL_PROFILE_MISMATCH' and path.read_text()=='{"exposure_profile":"other"}'

def test_old_seven_whitelist_unchanged():
    from core301.pulse.v2.protocol_book import OPEN_INJURIES,RESERVED_ACTIONS
    assert len(OPEN_INJURIES)==7 and not set(PROFILES)&set(OPEN_INJURIES)
    assert 'chest_tube' in RESERVED_ACTIONS


def test_conditional_monitoring_requires_explicit_grant(tmp_path):
    r=ExposureValidationRuntime(patient_id='P',run_id='R',directory=tmp_path,mode='research',validation_only=True)
    try:
        assert not r._access.visible() and r.observation_access is False
    finally:r.close()
