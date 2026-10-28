import copy
import pytest
from core301.dispatch.minimal.api import load_config,load_cases,build_input,read,CONFIG
from core301.dispatch.minimal.validation import validate_schedule

@pytest.fixture
def data():
 r,m=load_config();return build_input(r,m,load_cases(),horizon_min=60),read(CONFIG/'example_schedule.json')

def only(s,pids):
 s['selections']={p:f'{p}-plan-1' for p in pids};s['operations']=[];s['care']=[];s['transports']=[]
 template=next(x for x in s['patient_results'] if x['status']=='unscheduled')
 s['patient_results']=[dict(copy.deepcopy(template),patient_id=f'P{i:02}') if f'P{i:02}' not in pids else dict(patient_id=f'P{i:02}',status='scheduled') for i in range(1,17)]

def op(pid,n,loc,start,end,staff,space,consumables,**kw):
 return dict(task_id=f'{pid}-{n}',patient_id=pid,plan_id=f'{pid}-plan-1',action_id=f'{pid}-plan-1-a{n}',location=loc,start_min=start,end_min=end,staff_ids=staff,space_id=space,consumables=consumables,**kw)

def test_exact_inventory():
 r,_=load_config();expected={'A':[1000,0,60],'B':[500,0,60],'H1':[1500,1000,120],'H2':[500,500,60],'V1':[500,0,30],'V2':[500,0,30],'V3':[500,0,30]}
 actual={loc:[r['inventory'][loc][k]['quantity'] for k in ['saline','blood','oxygen']] for loc in expected}
 assert actual==expected and [sum(v[i] for v in actual.values()) for i in range(3)]==[5000,1500,390]

def test_full_courses_at_horizon_cannot_share_one_bag(data):
 ctx,s=data;only(s,['P08','P15'])
 s['operations']=[op('P08',1,'B',54,59,['B-basic-1'],'B-observation-1',{'infusion_set':1,'iv_access_kit':1}),op('P15',1,'B',50,53,['B-basic-2'],'B-treatment-1',{'external_bleeding_kit':1}),op('P15',2,'B',54,59,['B-basic-2'],'B-observation-2',{'infusion_set':1,'iv_access_kit':1})]
 before=copy.deepcopy(ctx);v=validate_schedule(ctx,s)
 assert {x['code'] for x in v['conflicts']}=={'STOCK_SHORTAGE'}
 assert any(x['resource_id']=='B:saline' for x in v['conflicts'])
 assert ctx==before
 # Removing an unstarted candidate cancels its reservation; no state was committed.
 only(s,['P08']);s['operations']=[op('P08',1,'B',54,59,['B-basic-1'],'B-observation-1',{'infusion_set':1,'iv_access_kit':1})]
 v=validate_schedule(ctx,s);assert v['known_constraints_passed'],v['conflicts']
 x=next(x for x in v['projected_inventory_changes'] if x['item']=='saline')
 assert (x['committed_quantity'],x['quantity'],x['after'],x['patient_bound_remaining'],x['available_after'])==(500,100,400,400,0)
 ctx['resources']['inventory']['B']['saline']['quantity']=499
 assert any(x['code']=='STOCK_SHORTAGE' for x in validate_schedule(ctx,s)['conflicts'])

def test_consumed_volume_is_not_debited_twice_and_oxygen_48_minutes(data):
 ctx,s=data;before=copy.deepcopy(ctx);v=validate_schedule(ctx,s)
 assert v['known_constraints_passed'] and ctx==before
 changes=v['projected_inventory_changes']
 saline=next(x for x in changes if x['item']=='saline' and x['location']=='A')
 assert (saline['committed_quantity'],saline['quantity'],saline['after'],saline['reserved_after'])==(500,500,500,0)
 oxygen=next(x for x in changes if x['item']=='oxygen')
 assert (oxygen['quantity'],oxygen['before'],oxygen['after'])==(24,60,36)
 ctx['resources']['inventory']['B']['oxygen']['quantity']=23
 assert any(x['code']=='STOCK_SHORTAGE' and x['resource_id']=='B:oxygen' for x in validate_schedule(ctx,s)['conflicts'])

def test_mv_exclusion_keeps_all_other_constraints(data):
 ctx,s=data;trip=copy.deepcopy(s['transports'][0]);only(s,['P03']);trip.update(patient_id='P03');s['transports']=[trip]
 s['operations']=[op('P03',1,'H1',20,28,['H1-advanced-1','H1-basic-1'],'H1-treatment-1',{'intubation_kit':1},equipment_ids=['H1-intubation_set-1']),op('P03',2,'H1',28,33,['H1-advanced-1'],'H1-ventilation_bed-1',{'breathing_circuit':1},equipment_ids=['H1-ventilator-1'])]
 s['care']=[dict(task_id=f'care-{t}',operation_id='P03-2',patient_id='P03',location='H1',start_min=t,end_min=t+2,staff_id='H1-care-1') for t in [38,43,48,53,58]]
 ctx['resources']['inventory']['H1']['oxygen']['quantity']=0
 v=validate_schedule(ctx,s);assert v['known_constraints_passed'],v['conflicts']
 assert 'MV_OXYGEN_OUT_OF_SCOPE' in {x['code'] for x in v['unchecked']}
 assert not any(x['item']=='oxygen' for x in v['projected_inventory_changes'])
 ids={x['resource_id'] for x in v['projected_occupancy']}
 assert {'H1-ventilator-1','H1-ventilation_bed-1','H1-advanced-1','H1-care-1'}<=ids
 s['operations'][1]['equipment_ids']=[]
 assert 'EQUIPMENT_REQUIREMENT' in {x['code'] for x in validate_schedule(ctx,s)['conflicts']}

@pytest.mark.parametrize('field,value',[('inventory',{}),('dose',1),('rate',0),('reservation_quantity',0)])
def test_model_cannot_override_bulk_parameters(data,field,value):
 ctx,s=data;s['operations'][1][field]=value
 assert 'SCHEMA_INVALID' in {x['code'] for x in validate_schedule(ctx,s)['conflicts']}

def test_continuation_does_not_create_second_course_or_hide_handoff(data):
 ctx,s=data;only(s,['P08'])
 first=op('P08',1,'B',54,59,['B-basic-1'],'B-observation-1',{'infusion_set':1,'iv_access_kit':1})
 continuation=dict(first,task_id='continue-P08',mode='continue',continuation_of=first['task_id'],location='V2',start_min=59,end_min=60,staff_ids=['V2-medic-1'],space_id='V2-stretcher-1',consumables={})
 s['operations']=[first,continuation]
 v=validate_schedule(ctx,s)
 # This is deliberately an unresolved handoff: don't grant movement/continuity.
 assert 'PATIENT_LOCATION' in {x['code'] for x in v['conflicts']}
 assert 'SUPPORT_HANDOFF_UNCHECKED' in {x['code'] for x in v['unchecked']}
 assert 'STOCK_SHORTAGE' not in {x['code'] for x in v['conflicts']}
 assert not any(x['code'] in ('BULK_USAGE_UNCHECKED','INVENTORY_UNCHECKED') and x['task_id']=='continue-P08' for x in v['unchecked'])
