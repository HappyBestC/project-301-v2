import asyncio
import json
import pytest
from pydantic import ValidationError
from tests.v2.test_runtime import SessionFaultFixture, injury
from core301.pulse.observation_projector import REQUESTS,BASIC,ObservationAccess
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.dispatch.shared_resources import SharedResourceManager
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.eta import FakeEtaProvider
from core301.research_runtime.runner import make_plan,dispatch_input,RecordedFixedProvider
from core301.research_runtime.bridge import SharedAuthority,CompleteExecutionBridge,executor_plan
from core301.research_runtime.evaluation import verify_rules


class Harness:
    def __init__(self,tmp_path,count=1):
        self.plan=make_plan('r','P');self.session=SessionFaultFixture()
        self.manager=SharedResourceManager();rs,ls=research_scene({'medic':count});self.manager.create_run('r',rs,ls)
        self.coord=SharedDispatchCoordinator(self.manager)
        self.auth=SharedAuthority(self.plan,self.coord,self.session.get_simulation_time,tmp_path)
        fields=frozenset(REQUESTS)-frozenset(BASIC)-{'neurologic.intracranial_pressure'}
        self.rt=CaseRuntime('P',tmp_path/'runtime',run_id='r',mode='research',session=self.session,
                           resources=self.auth,access=ObservationAccess(fields,fields,fields))
        self.rt.prepare(injury());self.bridge=CompleteExecutionBridge(self.rt,self.auth)
        self.coord.register_run('r',[dispatch_input(self.plan,self.rt.observe())],at_s=180.,patient_locations={'P':'scene'})
        self.provider=RecordedFixedProvider('P',tmp_path)
    def schedule(self,req=None):
        result=asyncio.run(self.coord.schedule_complete(req or self.auth.request('schedule'),self.plan,self.provider,FakeEtaProvider({})))
        if result.allocated:self.auth.task_id=result.task.task_id
        return result
    def execute(self):
        self.context=self.rt.build_context()
        return self.bridge.execute(self.plan,request_id='exec',context_ref=self.context.context_ref)
    def snap(self):
        s=self.manager.get_snapshot('r')
        for r in s['resources'].values():
            assert r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty']==r['total_qty']
            assert r['available_qty']+r['reserved_qty']+r['in_use_qty']+r['unavailable_qty']==r['total_qty']
        return s


def test_complete_plan_real_manager_executor_mapping_and_release(tmp_path):
    h=Harness(tmp_path);assert h.schedule().allocated
    assert json.loads((tmp_path/'agent_received_plan.json').read_text())==h.plan.model_dump(mode='json')
    rec=h.execute();item=rec['actions'][0]
    assert item['accepted'] and h.session.treatments==1
    assert item['native_payload']['PatientAction']['Hemorrhage']=={'Type':'External','Compartment':'RightLeg','Severity':{'Scalar0To1':{'Value':0}}}
    assert h.snap()['resources']['medic']['in_use_qty']==1
    h.rt.advance(1.);h.auth.finish(h.rt.query('exec'))
    assert h.snap()['resources']['medic']['available_qty']==1
    assert h.snap()['resources']['medic']['consumed_qty']==0
    assert all(e['action_instance_id']==h.plan.actions[0].action_instance_id for e in h.auth.events)


def test_insufficient_resource_never_submits_treatment(tmp_path):
    h=Harness(tmp_path,0);assert not h.schedule().allocated
    with pytest.raises(Exception):h.execute()
    assert h.session.treatments==0 and not h.snap()['allocations']


def test_no_dispatch_no_treatment(tmp_path):
    h=Harness(tmp_path)
    with pytest.raises(Exception):h.execute()
    assert h.session.treatments==0


def test_duplicate_schedule_and_execute_are_exactly_once(tmp_path):
    h=Harness(tmp_path);req=h.auth.request('schedule');a=h.schedule(req);b=h.schedule(req)
    assert a.task.task_id==b.task.task_id and len(h.snap()['allocations'])==1
    x=h.execute();y=h.bridge.execute(h.plan,request_id='exec',context_ref=h.context.context_ref)
    assert x==y and h.session.treatments==1
    with pytest.raises(ValueError):h.bridge.execute(h.plan,request_id='new',context_ref=h.context.context_ref)
    assert h.session.treatments==1


@pytest.mark.parametrize('failure',['unknown','rejected'])
def test_failed_native_receipt_preserved_no_retry_or_release(tmp_path,failure):
    h=Harness(tmp_path);h.schedule()
    if failure=='unknown':h.session.unknown_at=1
    else:h.session.fail_at=1
    with pytest.raises(Exception):h.execute()
    s=h.snap();state=s['plans'][h.plan.plan_id]['actions'][h.plan.actions[0].action_instance_id]
    assert state['execution']==failure
    h.rt.close()
    assert h.snap()['resources']['medic']['available_qty']==0
    h.bridge.execute(h.plan,request_id='exec',context_ref=h.context.context_ref)
    assert h.session.treatments==1
    with pytest.raises(ValueError):h.auth.finish(h.rt.query('exec'))


def test_accepted_alone_cannot_release(tmp_path):
    h=Harness(tmp_path);h.schedule();rec=h.execute()
    with pytest.raises(ValueError):h.auth.finish(rec)
    assert h.snap()['resources']['medic']['in_use_qty']==1


def test_task_cancelled_before_begin_blocks_native(tmp_path):
    h=Harness(tmp_path);result=h.schedule()
    h.coord.lifecycle(h.auth.request('cancel'),result.task.task_id,'cancel',detail='test cancellation')
    with pytest.raises(Exception):h.execute()
    assert h.session.treatments==0


@pytest.mark.parametrize('mutation',['target','dependency','extra_action','scope'])
def test_illegal_or_unsupported_plan_rejected_without_execution(tmp_path,mutation):
    h=Harness(tmp_path);h.schedule();p=h.plan.model_dump()
    actions=[dict(x) for x in p['actions']]
    if mutation=='target':actions[0]['compartment']='LeftLeg'
    if mutation=='dependency':actions[0]['depends_on']=('unknown',)
    if mutation=='extra_action':actions.append(dict(action_instance_id='fluid',action_type='fluid_resuscitation',side=None,compartment=None,depends_on=(actions[0]['action_instance_id'],)))
    if mutation=='scope':p['severity']=.6
    p['actions']=tuple(actions)
    with pytest.raises(ValueError):h.bridge.execute(p,request_id='exec',context_ref=h.rt.build_context().context_ref)
    assert h.session.treatments==0


def test_locked_rule_snapshot_and_definitions_unchanged():
    cfg=verify_rules();assert len(cfg['rules'])==14
    assert cfg['rules'][0]['P_supported'] is False


def test_runner_refuses_fake_native_evidence_before_creating_run():
    from core301.research_runtime.runner import run
    with pytest.raises(ValueError,match='real ResearchPulseSession'):
        asyncio.run(run(session_factory=SessionFaultFixture))


def test_initialization_failure_exports_not_called_without_fake_evaluation(monkeypatch):
    import tempfile
    from core301.paths import PROJECT_ROOT
    from core301.research_runtime.runner import run
    def fail(*args,**kwargs):raise RuntimeError('injected initialization failure before native engine')
    monkeypatch.setattr(CaseRuntime,'prepare',fail)
    with tempfile.TemporaryDirectory(prefix='test-loop-',dir=PROJECT_ROOT/'experiments/results') as directory:
        output,summary=asyncio.run(run(output_root=directory,run_id='failure-test'))
        result=json.loads((output/'evaluation_result.json').read_text())
        assert summary['real_pulse'] is False and summary['failure']['stage']=='initialization'
        assert result['evaluator_called'] is False and result['computation_state']=='NOT_RUN'
        assert json.loads((output/'native_action_results.json').read_text())==[]
