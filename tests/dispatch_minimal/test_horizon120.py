import copy
import pytest
from core301.dispatch.minimal.api import build_input, load_config, load_cases, read, CONFIG
from core301.dispatch.minimal.validation import validate_schedule


def data():
    r,m=load_config()
    return build_input(r,m,load_cases()), read(CONFIG/'example_schedule_120.json')


def codes(v):
    return {x['code'] for x in v['conflicts']}


def test_defaults_schema_and_boundaries():
    c,s=data()
    assert (c['observation_time_min'],c['horizon_min'])==(60,120)
    p=next(t for t in s['operations'] if t['patient_id']=='P04')
    p.update(start_min=119,end_min=120)
    v=validate_schedule(c,s)
    assert v['known_constraints_passed'],v['conflicts']
    assert next(p for p in v['observation_summary']['patients'] if p['patient_id']=='P04')['progress']=='not_started_waiting'
    assert next(p for p in v['planning_summary']['patients'] if p['patient_id']=='P04')['required_operations_completed']
    p.update(start_min=120,end_min=121)
    assert 'OUTSIDE_HORIZON' in codes(validate_schedule(c,s))
    with pytest.raises(ValueError):build_input(*load_config(),load_cases(),observation_time_min=121)


def test_persistent_occupancy_care_oxygen_and_no_mutation():
    c,s=data();before=copy.deepcopy(c);original=copy.deepcopy(s)
    v=validate_schedule(c,s)
    assert v['known_constraints_passed'] and not v['fully_verified']
    assert (c,s)==(before,original)
    for time,key,qty in [(60,'observation_summary',24),(120,'planning_summary',54)]:
        snap=v[key]
        assert snap['inventory']['B']['oxygen']['predicted_consumed']==qty
        assert snap['inventory']['B']['oxygen']['available_after_all_candidate_commitments']==6
        for rid in ['B-oxygen_device-1','B-observation-1','A-observation-1']:
            hold=next(x for x in snap['resource_occupancy'] if x['resource_id']==rid)
            assert hold['release_status']=='unknown' and hold['end_is_accounting_cutoff']
    assert any(x['start_min']>60 for x in v['required_care_tasks'])
    c['resources']['initial_reservations']=[dict(resource_id='B-care-1',start_min=62,end_min=63,patient_id='P05',task_id='existing',kind='operation')]
    assert 'RESOURCE_OVERLAP' in codes(validate_schedule(c,s))
    c['resources']['initial_reservations']=[]
    c['resources']['inventory']['B']['oxygen']['quantity']=53
    assert 'STOCK_SHORTAGE' in codes(validate_schedule(c,s))
    c['resources']['inventory']['B']['oxygen']['quantity']=60
    s['care']=[x for x in s['care'] if x['start_min']<60]
    assert 'CARE_MISSING' in codes(validate_schedule(c,s))


def test_infusion_two_snapshots_one_commitment():
    c,s=data()
    t=next(t for t in s['operations'] if t['patient_id']=='P01' and t['action_id'].endswith('a2'))
    t.update(start_min=54,end_min=59)
    s['care']=[x for x in s['care'] if x['patient_id']!='P01']
    for due in range(69,120,10):
        s['care'].append(dict(task_id=f'new-{due}',operation_id=t['task_id'],patient_id='P01',location='A',start_min=due,end_min=due+1,staff_id='A-care-1'))
    v=validate_schedule(c,s);assert v['known_constraints_passed'],v['conflicts']
    x=v['observation_summary']['inventory']['A']['saline'];y=v['planning_summary']['inventory']['A']['saline']
    assert (x['predicted_consumed'],x['unconsumed_commitment'],x['patient_bound_remaining'])==(100,400,400)
    assert (y['predicted_consumed'],y['unconsumed_commitment'])==(500,0)
    assert x['candidate_total_commitment']==y['candidate_total_commitment']==500
    assert x['available_after_all_candidate_commitments']==y['available_after_all_candidate_commitments']==500
    assert next(x for x in v['planning_summary']['resource_occupancy'] if x['resource_id']=='A-observation-1')['release_status']=='unknown'
    # Future commitments are unavailable at 60 even before the course starts.
    t.update(start_min=114,end_min=119);s['care']=[x for x in s['care'] if x['patient_id']!='P01']
    v=validate_schedule(c,s);assert v['known_constraints_passed'],v['conflicts']
    x=v['observation_summary']['inventory']['A']['saline'];y=v['planning_summary']['inventory']['A']['saline']
    assert (x['predicted_consumed'],x['future_not_started_commitment'])==(0,500)
    assert (y['predicted_consumed'],y['patient_bound_remaining'])==(100,400)
    assert x['available_after_all_candidate_commitments']==y['available_after_all_candidate_commitments']==500


def test_vehicle_reuse_after_sixty_and_location_snapshot():
    c,s=data();r=c['resources'];old=s['transports'][0]
    start=55;load=start+r['travel_min']['H1']['B'];depart=load+r['transport_min']['loading']
    arrive=depart+r['travel_min']['B']['H1'];handoff=arrive+r['transport_min']['handoff'];end=handoff+r['transport_min']['turnaround']
    trip=dict(task_id='trip-P11',patient_id='P11',vehicle_id='V1',departure_location='H1',pickup='B',destination='H1',start_min=start,load_start_min=load,depart_min=depart,arrive_min=arrive,handoff_end_min=handoff,end_min=end)
    s['transports'].append(trip);s['selections']['P11']='P11-plan-1'
    next(p for p in s['patient_results'] if p['patient_id']=='P11').update(status='scheduled')
    s['operations'].append(dict(task_id='op-P11',patient_id='P11',plan_id='P11-plan-1',action_id='P11-plan-1-a1',location='H1',start_min=handoff,end_min=handoff+3,staff_ids=['H1-basic-1'],space_id='H1-treatment-1',consumables={'decompression_kit':1}))
    v=validate_schedule(c,s);assert v['known_constraints_passed'],v['conflicts']
    assert v['observation_summary']['vehicles']['V1']['phase']=='empty_travel'
    assert v['planning_summary']['vehicles']['V1']==dict(location='H1',phase='idle',task_id=None)
    trip['departure_location']='A'
    assert 'VEHICLE_POSITION' in codes(validate_schedule(c,s))
    trip['departure_location']='H1';trip['end_min']=121
    assert 'OUTSIDE_HORIZON' in codes(validate_schedule(c,s))


def test_mv_holds_and_periods_after_sixty():
    c,s=data();template=copy.deepcopy(s['transports'][0]);template['patient_id']='P03'
    s['transports']=[template];s['selections']={'P03':'P03-plan-1'};s['care']=[]
    for p in s['patient_results']:
        p.update(status='scheduled' if p['patient_id']=='P03' else 'unscheduled',reason_code='no_feasible_schedule_found',reason='本测试仅核对通气持续资源，其他患者没有搜索安排。',considered_alternatives=['其他患者的完整方案未在此单项测试中搜索。'])
    s['operations']=[dict(task_id='intubate',patient_id='P03',plan_id='P03-plan-1',action_id='P03-plan-1-a1',location='H1',start_min=20,end_min=28,staff_ids=['H1-advanced-1','H1-basic-1'],space_id='H1-treatment-1',equipment_ids=['H1-intubation_set-1'],consumables={'intubation_kit':1}),dict(task_id='vent',patient_id='P03',plan_id='P03-plan-1',action_id='P03-plan-1-a2',location='H1',start_min=28,end_min=33,staff_ids=['H1-advanced-1'],space_id='H1-ventilation_bed-1',equipment_ids=['H1-ventilator-1'],consumables={'breathing_circuit':1})]
    for due in range(38,120,5):s['care'].append(dict(task_id=f'care-{due}',operation_id='vent',patient_id='P03',location='H1',start_min=due,end_min=due+2,staff_id='H1-care-1'))
    v=validate_schedule(c,s);assert v['known_constraints_passed'],v['conflicts']
    assert not v['fully_verified'] and 'MV_OXYGEN_OUT_OF_SCOPE' in {x['code'] for x in v['unchecked']}
    assert not any(x['item']=='oxygen' for x in v['projected_inventory_changes'])
    assert {'H1-ventilator-1','H1-ventilation_bed-1'}<={x['resource_id'] for x in v['planning_summary']['resource_occupancy']}
    s['care'][-1]['end_min']-=1
    assert {'CARE_TIMING','CARE_MISSING'}<=codes(validate_schedule(c,s))
