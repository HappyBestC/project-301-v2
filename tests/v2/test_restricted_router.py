import json
import pytest
from core301.runtime.v2.research_router import open_research_case
from core301.runtime.v2.restricted_registry import REGISTRY
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.runtime.v2.errors import V2Error
from core301.contracts.v2.restricted_observation import RestrictedObservation
from core301.runtime.v2.restricted_acceptance import safety_check
from core301.pulse.v2.protocol_book import OPEN_INJURIES

@pytest.mark.parametrize('kind',list(REGISTRY))
def test_production_denied_before_files(tmp_path,kind):
    p=tmp_path/'never'
    with pytest.raises(V2Error,match='research only'):open_research_case(kind,patient_id='P',run_id='R',directory=p)
    assert not p.exists()

@pytest.mark.parametrize('kind',list(OPEN_INJURIES))
def test_legacy_delegation(tmp_path,kind):
    r=open_research_case(kind,patient_id='P',run_id='R',directory=tmp_path/kind,mode='research')
    try:assert type(r) is CaseRuntime and not r._prepared and REGISTRY[kind].end_s==480
    finally:r.close()

@pytest.mark.parametrize('kind',['hemothorax','carbon_monoxide_exposure'])
def test_pending_no_side_effect(tmp_path,kind,monkeypatch):
    import dataclasses
    import core301.runtime.v2.research_router as router
    entries=dict(REGISTRY);entries[kind]=dataclasses.replace(entries[kind],admission='PENDING')
    monkeypatch.setattr(router,'REGISTRY',entries)
    p=tmp_path/'never'
    with pytest.raises(V2Error) as e:open_research_case(kind,patient_id='P',run_id='R',directory=p,mode='research')
    assert e.value.code=='ADMISSION_PENDING' and not p.exists()

def test_identity_and_lock(tmp_path):
    kw=dict(patient_id='P',run_id='R',directory=tmp_path/'case',mode='research')
    r=open_research_case('environmental_hypoxia',**kw)
    try:
        with pytest.raises(V2Error) as e:open_research_case('environmental_hypoxia',**kw)
        assert e.value.code=='SESSION_IN_USE'
    finally:r.close()
    with pytest.raises(V2Error) as e:open_research_case('carbon_monoxide_exposure',**kw,validation_only=True)
    assert e.value.code=='ROUTE_IDENTITY_MISMATCH'

def test_does_not_adopt_foreign_directory(tmp_path):
    p=tmp_path/'case';p.mkdir();(p/'foreign.json').write_text('{}')
    with pytest.raises(V2Error) as e:open_research_case('environmental_hypoxia',patient_id='P',run_id='R',directory=p,mode='research')
    assert e.value.code=='DIRECTORY_NOT_EMPTY' and (p/'foreign.json').read_text()=='{}'

# Real native observation fixture from preserved prior evidence, not a fabricated
# physiological trajectory. Mutations below test schema/safety refusal only.
def observation():
    from pathlib import Path
    p=Path('research_artifacts/v2_ten_injury_completion_program_v0.1/experiments/raw/runtime_attempt2/environmental_hypoxia/treated/observations.jsonl')
    x=json.loads(p.read_text().splitlines()[-1]);s=x['exposure_observation']
    return RestrictedObservation(injury_type='environmental_hypoxia',patient_id=s['patient_id'],session_epoch=s['session_epoch'],patient_observation=x['patient_observation'],specialty=s,aorta_sodium_mEq_L=s['aorta_sodium_mEq_L'],native_events=s['native_events'])

@pytest.mark.parametrize('event',['IrreversibleState','CardiacArrest','CardiovascularCollapse','CriticalBrainOxygenDeficit','HypovolemicShock','Hypernatremia','Hypoglycemia','ModerateHyperoxemia','UnrecognizedEvent'])
def test_event_veto_never_whitelist(event):
    o=observation();d=o.model_dump();d['native_events']={event:1.};d['specialty']['native_events']={event:1.}
    r=safety_check('environmental_hypoxia',[RestrictedObservation.model_validate(d)])
    assert not r['passed'] and event in r['all_event_names']

@pytest.mark.parametrize('field',['patient_id','session_epoch'])
def test_forged_identity(field):
    d=observation().model_dump();d[field]='foreign'
    with pytest.raises(ValueError):RestrictedObservation.model_validate(d)

def test_missing_physiology_rejects():
    d=observation().model_dump();d['patient_observation']['laboratory']['blood_ph']={'value':None,'status':'unavailable','observed_at_s':d['patient_observation']['simulation_time_s']}
    assert not safety_check('environmental_hypoxia',[RestrictedObservation.model_validate(d)])['passed']

def test_target_events_must_resolve():
    o=observation();d=o.model_dump();d['native_events']={'Hypoxia':10.};d['specialty']['native_events']={'Hypoxia':10.}
    early=RestrictedObservation.model_validate(d)
    assert safety_check('environmental_hypoxia',[early,o])['passed']
    assert not safety_check('environmental_hypoxia',[early])['passed']
    assert not safety_check('carbon_monoxide_exposure',[early,o])['passed']

def test_no_history_is_not_success():assert not safety_check('environmental_hypoxia',[])['passed']

@pytest.mark.parametrize('kind,event',[('environmental_hypoxia','Hypernatremia'),('carbon_monoxide_exposure','Hypoglycemia'),('carbon_monoxide_exposure','CardiacArrest'),('hemothorax','IrreversibleState')])
def test_risk_never_extends_to_other_events_or_hypoxia(kind,event):
    d=observation().model_dump();d['native_events']={event:1.};d['specialty']['native_events']={event:1.}
    assert not safety_check(kind,[RestrictedObservation.model_validate(d)],risk_conformance={'passed':True})['passed']

@pytest.mark.parametrize('event',['StartOfCardiacCycle','StartOfInhale','StartOfExhale'])
def test_cycle_markers_retained_without_becoming_pathology(event):
    d=observation().model_dump();d['native_events']={event:0.};d['specialty']['native_events']={event:0.}
    result=safety_check('environmental_hypoxia',[RestrictedObservation.model_validate(d)])
    assert result['passed'] and event in result['all_event_names'] and event in result['final_events']
