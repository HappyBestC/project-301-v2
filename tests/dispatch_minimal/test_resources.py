import copy
import json
import sys
import pytest
from core301.dispatch.minimal.api import build_input, load_cases, load_config, read, CONFIG, requirement
from core301.dispatch.minimal.validation import validate_schedule
from core301.dispatch.minimal.models import Schedule

@pytest.fixture
def fixture():
    resources,mapping=load_config()
    return build_input(resources,mapping,load_cases(),horizon_min=60),read(CONFIG/'example_schedule.json')

def codes(result,key='conflicts'):return {i['code'] for i in result[key]}

def test_document_totals_and_twelve_actions():
    r,m=load_config()
    assert len(r['personnel'])==26
    assert {k:sum(p['location']==k for p in r['personnel']) for k in r['nodes']}=={'A':4,'B':4,'H1':7,'H2':5}
    assert len(m['actions'])==12 and len(r['vehicles'])==3
    assert r['inventory']['B']['decompression_kit']['quantity']==1
    assert sum(r['inventory'][k]['saline']['quantity'] for k in r['inventory'])==5000
    assert len(r['service_capacities'])==2
    assert not any(x['type']=='research_hemostasis' for x in r['spaces'])
    assert sum(x['type']=='treatment' for x in r['spaces'])==7


def test_cases_projection_targets_and_clock(fixture):
    ctx,_=fixture
    assert len(ctx['patients'])==16
    for p in ctx['patients']:
        assert set(p['observation'])=={'patient_id','simulation_time_s','vitals'}
        assert 'severity' not in json.dumps(p)
        for pl in p['candidate_plans']:
            for a in pl['actions']:
                assert a['eligibility_status']=='eligibility_pending'
                if a['action_type'] in ('fluid_resuscitation','transfusion'):
                    assert a['target']=={'patient_id':p['patient_id']}
    p9=next(p for p in ctx['patients'] if p['patient_id']=='P09')
    assert p9['arrival_time_min']==10 and p9['pulse_sample_time_s']==pytest.approx(180)


def test_demo_partial_and_pure(fixture):
    ctx,s=fixture;before=copy.deepcopy(ctx);proposal=copy.deepcopy(s)
    result=validate_schedule(ctx,s)
    assert result['known_constraints_passed'] and not result['fully_verified']
    assert len(result['unscheduled_patient_ids'])==11
    assert ctx==before and s==proposal
    assert {'ELIGIBILITY_PENDING','STOP_CONDITION_UNCHECKED','TRANSFER_ELIGIBILITY_UNCHECKED'}<=codes(result,'unchecked')
    assert result['projected_vehicle_state']['V1']=={'location':'H1','available_from_min':25}
    assert result['projected_occupancy']
    assert not result['initial_state_mutated']


def test_staff_overlap(fixture):
    ctx,s=fixture;s['operations'][4]['staff_ids']=['A-basic-1']
    result=validate_schedule(ctx,s)
    assert 'RESOURCE_OVERLAP' in codes(result)
    assert any(i['resource_id']=='A-basic-1' and i['interval_min']==[0,1] for i in result['conflicts'])
    assert not result['projected_occupancy'] and not result['projected_inventory_changes']


def test_device_held_past_installation(fixture):
    ctx,s=fixture
    ctx['resources']['initial_reservations']=[{'resource_id':'B-oxygen_device-1','start_min':20,'end_min':25,'patient_id':'P05','task_id':'previous-reservation','kind':'support'}]
    result=validate_schedule(ctx,s)
    assert any(i['code']=='RESOURCE_OVERLAP' and i['resource_id']=='B-oxygen_device-1' and i['interval_min']==[20,25] for i in result['conflicts'])


def test_inventory_shortage(fixture):
    ctx,s=fixture;ctx['resources']['inventory']['B']['decompression_kit']['quantity']=0
    result=validate_schedule(ctx,s)
    assert 'STOCK_SHORTAGE' in codes(result)
    assert any(i['patient_id']=='P05' and i['resource_id']=='B:decompression_kit' for i in result['conflicts'])


def test_dependencies(fixture):
    ctx,s=fixture;s['operations'][1]['start_min']=0;s['operations'][1]['end_min']=5
    assert 'DEPENDENCY_UNMET' in codes(validate_schedule(ctx,s))


def test_location_capability(fixture):
    ctx,s=fixture;s['operations'][5]['location']='V2'
    assert 'LOCATION_UNSUPPORTED' in codes(validate_schedule(ctx,s))


def test_arrival_and_resource_location(fixture):
    ctx,s=fixture;s['operations'][-1]['start_min']=0;s['operations'][-1]['end_min']=2
    s['operations'][-1]['staff_ids']=['A-basic-2']
    assert {'BEFORE_ARRIVAL','RESOURCE_LOCATION'}<=codes(validate_schedule(ctx,s))


def test_transport_time_and_position(fixture):
    ctx,s=fixture;s['transports'][0]['arrive_min']=12
    assert 'TRANSPORT_TIMING' in codes(validate_schedule(ctx,s))
    s['transports'][0]['departure_location']='B'
    assert 'VEHICLE_POSITION' in codes(validate_schedule(ctx,s))


def test_second_trip_uses_last_destination(fixture):
    ctx,s=fixture;ctx['horizon_min']=120
    s['selections']={};s['operations']=[];s['care']=[]
    trip={'task_id':'second','patient_id':'P06','vehicle_id':'V1','departure_location':'H1','pickup':'B','destination':'H2','start_min':25,'load_start_min':45,'depart_min':48,'arrive_min':58,'handoff_end_min':63,'end_min':68}
    s['transports'].append(trip)
    result=validate_schedule(ctx,s)
    # Transport timing is sound, but transport-only outcomes are now rejected.
    assert not ({'VEHICLE_POSITION','TRANSPORT_TIMING','VEHICLE_OVERLAP'} & codes(result))
    assert 'SCHEDULED_PLAN_MISSING' in codes(result)
    trip['departure_location']='A'
    assert 'VEHICLE_POSITION' in codes(validate_schedule(ctx,s))


def test_vehicle_overlap(fixture):
    ctx,s=fixture;t=copy.deepcopy(s['transports'][0]);t.update(task_id='second',patient_id='P01')
    s['transports'].append(t)
    result=validate_schedule(ctx,s)
    assert {'VEHICLE_OVERLAP','RESOURCE_OVERLAP'}<=codes(result)


def test_periodic_care_is_not_free(fixture):
    ctx,s=fixture;s['care']=[]
    assert 'CARE_MISSING' in codes(validate_schedule(ctx,s))


def test_no_forged_supply_or_existing_access(fixture):
    ctx,s=fixture;s['operations'][1]['consumables']={}
    s['operations'][1]['access_mode']='existing'
    assert {'CONSUMABLE_MAPPING_MISMATCH','ACCESS_NOT_ESTABLISHED'}<=codes(validate_schedule(ctx,s))


def test_research_capacity_is_shared_across_treatment_positions(fixture):
    ctx,s=fixture
    ctx['resources']['initial_reservations']=[{'resource_id':'H1-research_hemostasis-1','start_min':25,'end_min':30,'patient_id':'P07','task_id':'other-surgery','kind':'service_capacity'}]
    s['operations'][2]['space_id']='H1-treatment-2'
    result=validate_schedule(ctx,s)
    assert any(i['code']=='RESOURCE_OVERLAP' and i['resource_id']=='H1-research_hemostasis-1' for i in result['conflicts'])


def test_nonfinite_and_extra_override_rejected(fixture):
    ctx,s=fixture;s['operations'][0]['start_min']=float('nan')
    assert 'SCHEMA_INVALID' in codes(validate_schedule(ctx,s))
    s['operations'][0]['start_min']=0;s['operations'][0]['dose']=1
    assert 'SCHEMA_INVALID' in codes(validate_schedule(ctx,s))


def test_transfusion_access_phase_is_single_person(fixture):
    ctx,_=fixture
    action=next(a for p in ctx['patients'] if p['patient_id']=='P02' for pl in p['candidate_plans'] for a in pl['actions'] if a['action_type']=='transfusion')
    req=requirement(ctx['action_mapping'],action)
    assert req['duration_min']==11 and req['access_phase_min']==3
    assert req['staff_roles']==['transfusion','transfusion']
    assert requirement(ctx['action_mapping'],action,access_mode='existing')['duration_min']==8


def test_incomplete_selected_plan_is_reported(fixture):
    ctx,s=fixture;s['operations'].pop(1)
    assert 'PLAN_ACTION_MISSING' in codes(validate_schedule(ctx,s))


def test_known_stock_consumption_is_projection_only(fixture):
    ctx,s=fixture;before=ctx['resources']['inventory']['B']['decompression_kit']['quantity']
    result=validate_schedule(ctx,s)
    item=next(x for x in result['projected_inventory_changes'] if x['item']=='decompression_kit')
    assert item['before']==1 and item['after']==0
    assert ctx['resources']['inventory']['B']['decompression_kit']['quantity']==before
    saline=next(x for x in result['projected_inventory_changes'] if x['item']=='saline')
    assert saline['quantity']==500 and saline['after']==500 and saline['checked']


def test_pending_not_accepted_for_real_execution(fixture):
    ctx,s=fixture;s['demonstration_only']=False
    assert 'ELIGIBILITY_REQUIRED' in codes(validate_schedule(ctx,s))


def test_existing_agent_batch_bridge_uses_schema_and_validator(fixture,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import openai
    from core301.dispatch.providers import LLMDispatchProvider
    ctx,s=fixture;calls=[]
    class Client:
        def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(s)))])
    monkeypatch.setattr(openai,'AsyncOpenAI',Client)
    provider=object.__new__(LLMDispatchProvider)
    provider._config=SimpleNamespace(base_url='https://mock.invalid',api_key='mock',model='mock')
    result=asyncio.run(provider.decide_resource_schedule(ctx))
    sent=json.loads(calls[0]['messages'][1]['content'])
    assert len(sent['patients'])==16 and 'output_json_schema' in sent
    assert result['validation']['known_constraints_passed']
    assert all(set(p['observation'])=={'patient_id','simulation_time_s','vitals'} for p in sent['patients'])


def test_position_capacity_reserved_until_horizon(fixture):
    ctx,s=fixture
    ctx['resources']['initial_reservations']=[{'resource_id':'A-observation-1','start_min':25,'end_min':30,'patient_id':'P09','task_id':'other-patient','kind':'space'}]
    result=validate_schedule(ctx,s)
    assert any(i['code']=='RESOURCE_OVERLAP' and i['resource_id']=='A-observation-1' for i in result['conflicts'])


def test_transport_cannot_start_before_patient_arrival(fixture):
    ctx,s=fixture;s['transports'][0]['patient_id']='P09'
    assert 'BEFORE_ARRIVAL' in codes(validate_schedule(ctx,s))


def test_transfusion_full_phase_allocation(fixture):
    ctx,s=fixture
    # Replace P02's fixed alternative only in the candidate proposal, not its source plan.
    s['selections']['P02']='P02-plan-2'
    for t in s['operations']:
        if t['patient_id']=='P02':
            t['plan_id']='P02-plan-2';t['action_id']=t['action_id'].replace('plan-1','plan-2')
    infusion=s['operations'][3]
    infusion.update(end_min=46,staff_ids=['H1-basic-1','H1-care-1'],access_staff_id='H1-basic-1',consumables={'transfusion_set':1,'iv_access_kit':1})
    s['care']=[x for x in s['care'] if x['patient_id']!='P02']
    for due in [51,56]:
        s['care'].append({'task_id':f'transfusion-care-{due}','operation_id':infusion['task_id'],'patient_id':'P02','location':'H1','start_min':due,'end_min':due+1,'staff_id':'H1-care-1'})
    result=validate_schedule(ctx,s)
    assert result['known_constraints_passed'],result['conflicts']
    periods=[(h['resource_id'],h['start_min'],h['end_min']) for h in result['projected_occupancy'] if h['task_id']==infusion['task_id'] and h['resource_id'] in ['H1-basic-1','H1-care-1']]
    assert ('H1-basic-1',35,38) in periods and ('H1-basic-1',38,46) in periods and ('H1-care-1',38,46) in periods
    assert ('H1-care-1',35,46) not in periods
