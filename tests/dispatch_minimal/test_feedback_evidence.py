import copy
from pathlib import Path
from core301.dispatch.minimal.api import read
from core301.dispatch.minimal.validation import validate_schedule
from core301.dispatch.minimal.feedback import build_feedback
from core301.dispatch.minimal.personnel_evidence import personnel_evidence

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'runs/medical_resources_horizon120_001'

def old(n=2):
    return read(OLD/'dispatch_input.json'),read(OLD/f'attempt_{n:02}/candidate_schedule.json')

def group(v,pid='P09'):
    return next(g for g in v['personnel_evidence']['groups'] if g['patient_id']==pid and g['required_capabilities']==['infusion_care'])

def test_real_capabilities_and_calendar_not_role_names():
    c,s=old();before=copy.deepcopy((c,s));v=validate_schedule(c,s)
    g=group(v);assert g['required_capabilities']==['infusion_care'] and len(g['segments'])==10
    for sid in ['A-basic-1','A-basic-2']:
        row=next(x for x in g['candidates'] if x['personnel_id']==sid)
        assert all(x['availability']=='free_for_this_interval' for x in row['segments'])
    row=next(x for x in g['candidates'] if x['personnel_id']=='A-care-1')
    assert all(x['availability']=='unavailable' and x['conflicting_tasks'] for x in row['segments'])
    assert (c,s)==before

def test_unavailable_location_and_initial_reservation():
    c,s=old()
    next(p for p in c['resources']['personnel'] if p['id']=='A-basic-2')['status']='unavailable'
    c['resources']['initial_reservations']=[dict(resource_id='A-basic-1',start_min=28,end_min=29,patient_id='P04',task_id='initial-task',kind='operation')]
    g=group(validate_schedule(c,s));rows={r['personnel_id']:r for r in g['candidates']}
    assert rows['A-basic-1']['segments'][0]['availability']=='unavailable'
    assert rows['A-basic-1']['segments'][0]['conflicting_tasks'][0]['task_id']=='initial-task'
    assert all(x['availability']=='unavailable' for x in rows['A-basic-2']['segments'])
    assert all(x['availability']=='unavailable' and 'RESOURCE_LOCATION' in x['reasons'] for x in rows['B-basic-1']['segments'])

def test_missing_care_marks_calendar_uncertain():
    c,s=old();s['care'].pop()
    g=group(validate_schedule(c,s))
    assert all(x['availability']=='undetermined' for r in g['candidates'] if r['personnel_id']=='A-basic-1' for x in r['segments'])

def test_history_live_fixed_and_withdrawn():
    c,s1=old(1);_,s2=old(2);_,s3=old(3);history={}
    v1=validate_schedule(c,s1);f1=build_feedback(c,s1,v1,1,history,set())
    v2=validate_schedule(c,s2);f2=build_feedback(c,s2,v2,2,history,set(s1['selections']))
    assert f2['conflicts']==v2['conflicts'] and f2['required_care_tasks']==v2['required_care_tasks']
    assert any(x['current_status']=='resolved_in_current_candidate' and x['conflict']['code']=='UNEXPECTED_ACCESS_STAFF' for x in f2['historical_conflicts'])
    assert any(x['current_status']=='not_triggered_after_withdrawal' and x['conflict']['patient_id']=='P11' for x in f2['historical_conflicts'])
    assert f2['withdrawn_this_round'][0]['patient_id']=='P11' and f2['withdrawn_this_round'][0]['prior_conflict_refs']
    live=build_feedback(c,s2,v2,3,copy.deepcopy(history),set(s2['selections']))
    assert any(x['current_status']=='still_present' and 'latest_conflict_index' in x and 'conflict' not in x for x in live['historical_conflicts'])
    v3=validate_schedule(c,s3);f3=build_feedback(c,s3,v3,3,history,set(s2['selections']))
    assert all(x['current_status']=='not_triggered_after_withdrawal' for x in f3['historical_conflicts'] if x.get('conflict',{}).get('patient_id')=='P09')
    assert f3['withdrawn_this_round'][0]['patient_id']=='P09'

def test_text_policy_changes_acceptance_not_actual_assignment_rules():
    c,s=old(3);v=validate_schedule(c,s)
    assert v['known_constraints_passed'] and v['scheduled_patients']==7 and not v['fully_verified']
    assert len(v['text_reference_hints'])==1 and v['text_reference_hints'][0]['resource_id']=='A-care-2'
    next(x for x in s['patient_results'] if x['patient_id']=='P09')['blocking_resources']=['A-care-2']
    assert any(x['code']=='REASON_UNKNOWN_REFERENCE' for x in validate_schedule(c,s)['conflicts'])
    c,s=old(1);v=validate_schedule(c,s)
    assert any(x['code']=='UNKNOWN_RESOURCE' and x['resource_id']=='A-care-2' for x in v['conflicts'])
    assert any(x['code']=='STOCK_SHORTAGE' for x in v['conflicts'])

def test_evidence_respects_phase_and_crew_intervals():
    # Use exact validator interval records for a real transfusion in the existing example.
    from core301.dispatch.minimal.api import load_config,load_cases,build_input,CONFIG
    c=build_input(*load_config(),load_cases(),horizon_min=60);s=read(CONFIG/'example_schedule.json')
    s['selections']['P02']='P02-plan-2'
    for t in s['operations']:
        if t['patient_id']=='P02':t['plan_id']='P02-plan-2';t['action_id']=t['action_id'].replace('plan-1','plan-2')
    t=next(x for x in s['operations'] if x['patient_id']=='P02' and x['action_id'].endswith('a2'))
    t.update(end_min=46,staff_ids=['H1-basic-1','H1-care-1'],access_staff_id='H1-basic-1',consumables={'transfusion_set':1,'iv_access_kit':1})
    s['care']=[x for x in s['care'] if x['patient_id']!='P02']
    for due in [51,56]:s['care'].append(dict(task_id=f'care-{due}',operation_id=t['task_id'],patient_id='P02',location='H1',start_min=due,end_min=due+1,staff_id='H1-care-1'))
    v=validate_schedule(c,s);assert not v['conflicts'],v['conflicts']
    holds=v['projected_occupancy'];people={x['id']:x for x in c['resources']['personnel']}
    def query(role,loc,start,end,pid='P04'):
        demand=dict(task_id='query',operation_id=None,patient_id=pid,location=loc,start_min=start,end_min=end,roles=[role],assigned_ids=['unknown'])
        evidence=personnel_evidence(people,[demand],holds,[dict(code='NOT_PERSONNEL',task_id='query',resource_id='unknown')],1e-8)
        return {x['personnel_id']:x['segments'][0] for x in evidence['groups'][0]['candidates']}
    assert query('transfusion','H1',35,38)['H1-care-1']['availability']=='free_for_this_interval'
    assert query('transfusion','H1',38,39)['H1-care-1']['availability']=='unavailable'
    assert query('access','H1',35,38)['H1-basic-1']['availability']=='unavailable'
    assert query('oxygen_care','V1',10,11)['V1-medic-1']['availability']=='unavailable'
    assert query('oxygen_care','V1',25,26)['V1-medic-1']['availability']=='free_for_this_interval'
    assert query('oxygen_care','V1',10,11,'P02')['V1-medic-1']['availability']=='free_for_this_interval'

def test_withdrawn_blocking_patient_is_not_called_repaired():
    c,s=old(2);v=validate_schedule(c,s);history={}
    build_feedback(c,s,v,1,history,set())
    reduced=copy.deepcopy(s)
    del reduced['selections']['P01']
    reduced['operations']=[t for t in reduced['operations'] if t['patient_id']!='P01']
    reduced['care']=[t for t in reduced['care'] if t['patient_id']!='P01']
    next(p for p in reduced['patient_results'] if p['patient_id']=='P01').update(status='unscheduled',reason_code='no_feasible_schedule_found',reason='本测试撤下该患者，未完成任何替代方案的排程核对。',considered_alternatives=['尚未完成替代人员、时段或转运安排的检查。'])
    f=build_feedback(c,reduced,validate_schedule(c,reduced),2,history,set(s['selections']))
    assert all(x['current_status']=='not_triggered_after_withdrawal' for x in f['historical_conflicts'])
    assert f['withdrawn_this_round'][0]['patient_id']=='P01'
    assert len(f['withdrawn_this_round'][0]['prior_conflict_refs'])==10
