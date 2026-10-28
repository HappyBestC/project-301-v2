import asyncio
import copy
import pytest
from core301.dispatch.minimal.api import build_input,load_config,load_cases,read,CONFIG
from core301.dispatch.minimal.validation import validate_schedule
from core301.dispatch.minimal.agent_run import run_agent
from dispatch_minimal.test_agent_run import ScriptedProvider

@pytest.fixture
def data():
    r,m=load_config()
    return build_input(r,m,load_cases(),horizon_min=60),read(CONFIG/'example_schedule.json')

def codes(ctx,s):return {x['code'] for x in validate_schedule(ctx,s)['conflicts']}

def test_missing_p11(data):
    ctx,s=data;s['patient_results']=[x for x in s['patient_results'] if x['patient_id']!='P11']
    v=validate_schedule(ctx,s)
    assert 'PATIENT_RESULT_MISSING' in {x['code'] for x in v['conflicts']}
    assert not v['all_patients_accounted_for'] and v['outcome_status']=='结果不完整'

@pytest.mark.parametrize('pid,code',[('P01','PATIENT_RESULT_DUPLICATE'),('P99','PATIENT_RESULT_UNKNOWN')])
def test_duplicate_or_unknown(data,pid,code):
    ctx,s=data;x=copy.deepcopy(s['patient_results'][0]);x['patient_id']=pid;s['patient_results'].append(x)
    assert code in codes(ctx,s)

@pytest.mark.parametrize('remove_plan',[True,False])
def test_scheduled_requires_complete_plan(data,remove_plan):
    ctx,s=data
    if remove_plan:del s['selections']['P01']
    else:s['operations']=[x for x in s['operations'] if x['patient_id']!='P01']
    assert ('SCHEDULED_PLAN_MISSING' if remove_plan else 'PLAN_ACTION_MISSING') in codes(ctx,s)

@pytest.mark.parametrize('reason',['','未安排','资源不足'])
def test_specific_reason_required(data,reason):
    ctx,s=data;next(x for x in s['patient_results'] if x['patient_id']=='P11')['reason']=reason
    assert 'UNSCHEDULED_REASON_REQUIRED' in codes(ctx,s)

@pytest.mark.parametrize('field,value',[('blocking_resources',['B:imaginary_kit']),('reason','P99需要在H9操作，但V9无法及时接送该患者。')])
def test_reason_references_must_exist(data,field,value):
    ctx,s=data;next(x for x in s['patient_results'] if x['patient_id']=='P11')[field]=value
    v=validate_schedule(ctx,s)
    if field=='blocking_resources':
        assert 'REASON_UNKNOWN_REFERENCE' in {x['code'] for x in v['conflicts']}
    else:
        assert not v['conflicts'] and not v['fully_verified']
        assert v['text_reference_hints']

def test_unscheduled_cannot_keep_tasks(data):
    ctx,s=data;result=s['patient_results'][0];result.update(status='unscheduled',reason_code='no_feasible_schedule_found',reason='尚未找到该患者全部动作及持续照护的完整安排。',considered_alternatives=['已考虑延后操作，但尚未排好后续照护。'])
    assert 'UNSCHEDULED_HAS_TASKS' in codes(ctx,s)

def test_partial_counts_and_original_conflicts(data):
    ctx,s=data;v=validate_schedule(ctx,s)
    assert (v['loaded_patients'],v['accounted_patients'],v['scheduled_patients'],v['unscheduled_patients'])==(16,16,5,11)
    assert v['all_patients_accounted_for'] and not v['all_patients_scheduled']
    assert v['outcome_status']=='部分调度，原因已说明' and not v['fully_verified']
    s['operations'][4]['staff_ids']=['A-basic-1']
    assert 'RESOURCE_OVERLAP' in codes(ctx,s)

def test_removed_conflict_patient_stays_accounted_in_feedback(data,tmp_path):
    ctx,good=data;bad=copy.deepcopy(good);bad['operations'][4]['staff_ids']=['A-basic-1']
    pid=bad['operations'][4]['patient_id'];partial=copy.deepcopy(good)
    del partial['selections'][pid]
    partial['operations']=[x for x in partial['operations'] if x['patient_id']!=pid]
    partial['care']=[x for x in partial['care'] if x['patient_id']!=pid]
    result=next(x for x in partial['patient_results'] if x['patient_id']==pid)
    result.update(status='unscheduled',reason_code='no_feasible_schedule_found',reason='原操作人员在该时段与其他患者冲突，本次尚未找到完整替代排程。',blocking_resources=['A-basic-1'],considered_alternatives=['已考虑调整时间和更换人员，尚未提交完整可行安排。'])
    provider=ScriptedProvider([bad,partial,partial])
    summary=asyncio.run(run_agent(provider,ctx,tmp_path/'run',max_attempts=3))
    feedback=provider.calls[2]['feedback']
    assert pid in feedback['withdrawn_or_unscheduled_patients']
    assert any(x.get('conflict',{}).get('patient_id')==pid and x['current_status']=='not_triggered_after_withdrawal' for x in feedback['historical_conflicts'])
    assert summary['status']=='partial_schedule' and not summary['all_patients_scheduled']
    assert summary['scheduled_patients']==4 and summary['accounted_patients']==16

def test_later_conflict_retains_auditable_valid_partial(data,tmp_path):
    ctx,good=data;bad=copy.deepcopy(good);bad['operations'][4]['staff_ids']=['A-basic-1']
    provider=ScriptedProvider([good,bad])
    summary=asyncio.run(run_agent(provider,ctx,tmp_path/'run',max_attempts=2))
    assert summary['accepted_attempt']==1 and summary['last_attempt_conflicts']>0
    assert summary['status']=='partial_schedule' and summary['known_constraints_passed']

def test_all_scheduled_still_does_not_confirm_eligibility(data):
    ctx,s=data
    ctx['patients']=[p for p in ctx['patients'] if p['patient_id'] in s['selections']]
    s['patient_results']=[x for x in s['patient_results'] if x['status']=='scheduled']
    v=validate_schedule(ctx,s)
    assert v['all_patients_scheduled'] and v['known_constraints_passed']
    assert v['outcome_status']=='全员排程通过已知约束' and not v['fully_verified']

def test_all_unscheduled_is_never_full_scheduling(data):
    ctx,s=data
    s['selections']={};s['operations']=[];s['care']=[];s['transports']=[]
    template=next(x for x in s['patient_results'] if x['status']=='unscheduled')
    s['patient_results']=[dict(copy.deepcopy(template),patient_id=p['patient_id']) for p in ctx['patients']]
    v=validate_schedule(ctx,s)
    assert v['known_constraints_passed'] and v['all_patients_accounted_for']
    assert v['scheduled_patients']==0 and not v['all_patients_scheduled']
    assert v['outcome_status']=='部分调度，原因已说明'
