"""M3-A offline evidence only. HTTP/Pulse substitutes are explicitly mocked."""
import asyncio
import copy
import json
import tempfile
from types import SimpleNamespace
import httpx
import openai
import pytest
from core301.agent.complete_decision import agent_input, parse_decision, build_complete_plan
from core301.agent import complete_provider as provider
from core301.pulse.observation_projector import ObservationProjector, BASIC, Sample
from core301.research_runtime.m3a_runner import RealWorkflow, run, STAGES
from core301.research_runtime.runner import dispatch_input, RecordedFixedProvider
from core301.research_runtime.bridge import SharedAuthority, CompleteExecutionBridge
from core301.dispatch.shared_resources import SharedResourceManager
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.eta import FakeEtaProvider
from core301.paths import PROJECT_ROOT
from tests.v2.test_runtime import runtime

DRAFT={'schema_version':'301.treatment.decision.m3a.1','decision_type':'propose_plan',
       'actions':[{'action_type':'control_external_bleeding','compartment':'RightLeg'}],
       'reasoning_summary':'Mock explanation','refusal_reason':None}
KNOWN=[{'injury_type':'external_hemorrhage','compartment':'RightLeg'}]


def test_input_units_missing_and_no_truth_leak():
    obs=ObservationProjector().project('P',180,{'vitals.heart_rate':Sample(90,179)})
    data=agent_input(obs,'P',KNOWN)
    assert data['measurements']['vitals.heart_rate']==dict(value=90.,status='available',observed_at_s=179.,unit='1/min')
    assert data['measurements']['vitals.pulse_oximetry']==dict(value=None,status='unavailable',observed_at_s=None,unit='1')
    assert set(data['measurements'])==set(BASIC)
    assert not any(x in json.dumps(data) for x in ['severity','diagnostic','resource','grade','expected'])


@pytest.mark.parametrize('case',['patient','time','unauthorized','severity'])
def test_input_rejects_identity_or_grant_mismatch(case):
    obs=ObservationProjector().project('P',179 if case=='time' else 180,{})
    known=copy.deepcopy(KNOWN)
    if case=='unauthorized':known=[]
    if case=='severity':known[0]['severity']=.4
    with pytest.raises(ValueError):agent_input(obs,'other' if case=='patient' else 'P',known)


def test_plan_is_lossless_new_action_and_host_fields():
    draft=parse_decision(json.dumps(DRAFT));plan=build_complete_plan(draft,'r','P')
    assert plan.actions[0].action_type==draft.actions[0].action_type=='control_external_bleeding'
    assert plan.actions[0].compartment==draft.actions[0].compartment
    assert plan.actions[0].action_instance_id=='r-action-1'
    assert plan.severity==.4 and plan.parameter_policy=='fixed_profile_no_overrides'
    assert plan.actions[0].depends_on==() and plan.schema_version=='301.treatment.complete.1'


@pytest.mark.parametrize('mutation',['unknown','out_of_scope','empty','target','missing','extra','duplicate','sequence','native','version'])
def test_invalid_model_drafts_rejected(mutation):
    d=copy.deepcopy(DRAFT)
    if mutation=='unknown':d['actions'][0]['action_type']='magic'
    if mutation=='out_of_scope':d['actions'][0]={'action_type':'fluid_resuscitation'}
    if mutation=='empty':d['actions']=[]
    if mutation=='target':d['actions'][0]['compartment']='LeftLeg'
    if mutation=='missing':d.pop('reasoning_summary')
    if mutation=='extra':d['severity']=.4
    if mutation=='duplicate':d['actions']*=2
    if mutation=='sequence':d['actions'].insert(0,{'action_type':'mechanical_ventilation'})
    if mutation=='native':d['actions'][0]['Rate']=100
    if mutation=='version':d['schema_version']='301.treatment.complete.1'
    with pytest.raises(ValueError):parse_decision(json.dumps(d))


@pytest.mark.parametrize('content',['not JSON','```json\n{}\n```','{"actions":[],"actions":[]}'])
def test_nonjson_or_duplicate_keys_rejected(content):
    with pytest.raises(ValueError):parse_decision(content)


@pytest.mark.parametrize('kind',['defer','insufficient_evidence'])
def test_refusal_is_preserved_and_never_plan(kind):
    draft=parse_decision(json.dumps({**DRAFT,'decision_type':kind,'actions':[],'refusal_reason':'uncertain'}))
    assert draft.refusal_reason=='uncertain'
    with pytest.raises(ValueError,match='MODEL_'):build_complete_plan(draft,'r','P')


@pytest.fixture
def api(monkeypatch,tmp_path):
    monkeypatch.setattr(provider,'PROJECT_ROOT',tmp_path)
    for k,v in {'OPENAI_BASE_URL':'https://mock.invalid/v1','OPENAI_API_KEY':'mock-test-value','OPENAI_MODEL':'mock-model'}.items():
        monkeypatch.setenv(k,v)
    state={'requests':[],'content':json.dumps(DRAFT),'status':200}
    def respond(request):
        state['requests'].append(json.loads(request.content))
        if state['status']!=200:return httpx.Response(state['status'],json={'error':{'message':'mock-test-value'}})
        return httpx.Response(200,json={'id':'mock-id','object':'chat.completion','created':0,'model':'mock-model',
             'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':state['content']}}],
             'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
    def client(**kwargs):
        assert kwargs['max_retries']==0 and kwargs['timeout']==60
        return openai.OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(provider,'OpenAI',client)
    return state


def test_http_request_raw_response_usage_and_no_secret(api,tmp_path):
    payload=agent_input(ObservationProjector().project('P',180,{}),'P',KNOWN)
    p=provider.LLMCompleteTreatmentProvider()
    assert p.create_decision(payload,tmp_path)==json.dumps(DRAFT)
    assert json.loads(api['requests'][0]['messages'][1]['content'])==payload
    raw=json.loads((tmp_path/'llm_response.json').read_text())
    assert raw['response']['usage']['total_tokens']==30 and raw['cost'] is None
    assert 'mock-test-value' not in ''.join(f.read_text() for f in tmp_path.iterdir())
    with pytest.raises(RuntimeError):p.create_decision(payload,tmp_path)
    assert len(api['requests'])==1


@pytest.mark.parametrize('failure',['http','timeout','empty'])
def test_api_failures_no_retry_or_sensitive_error(api,tmp_path,monkeypatch,failure):
    if failure=='http':api['status']=503
    if failure=='empty':api['content']=''
    if failure=='timeout':
        def fail(**kwargs):raise TimeoutError('mock-test-value')
        monkeypatch.setattr(provider,'OpenAI',fail)
    with pytest.raises(RuntimeError):provider.LLMCompleteTreatmentProvider().create_decision({},tmp_path)
    assert len(api['requests'])<=1
    assert 'mock-test-value' not in (tmp_path/'llm_error.json').read_text()


@pytest.mark.parametrize('case',['success','no_resource','invalid','refusal','contract_failure'])
def test_workflow_to_existing_resource_and_execution_bridge(api,tmp_path,case,monkeypatch):
    rt=runtime(tmp_path/'case')
    # No fixed plan is used by this integration harness.
    rt.resources=None
    workflow=RealWorkflow();workflow.provider=provider.LLMCompleteTreatmentProvider()
    summary={'run_id':'r','decision_id':'r-decision','stages':{k:'NOT_RUN' for k in STAGES}}
    if case=='invalid':api['content']='not JSON'
    if case=='refusal':api['content']=json.dumps({**DRAFT,'decision_type':'defer','actions':[],'refusal_reason':'uncertain'})
    if case=='contract_failure':
        def fail(*args,**kwargs):raise ValueError('injected complete contract failure')
        monkeypatch.setattr('core301.agent.complete_decision.CompletePlan',fail)
    manager=SharedResourceManager();rs,ls=research_scene({'medic':0 if case=='no_resource' else 1})
    manager.create_run('r',rs,ls);coord=SharedDispatchCoordinator(manager)
    if case in ('invalid','refusal','contract_failure'):
        with pytest.raises(ValueError):workflow.decide(rt,rt.observe(),tmp_path,summary,{})
        assert rt.session.treatments==0 and not manager.get_snapshot('r')['allocations']
        assert len(api['requests'])==1
        return
    plan=workflow.decide(rt,rt.observe(),tmp_path,summary,{})
    sent=json.loads(api['requests'][0]['messages'][1]['content'])
    assert sent['measurements']['vitals.heart_rate']['value']==rt.observe().vitals.heart_rate.value
    authority=SharedAuthority(plan,coord,rt.session.get_simulation_time,tmp_path);rt.resources=authority
    bridge=CompleteExecutionBridge(rt,authority)
    coord.register_run('r',[dispatch_input(plan,rt.observe())],at_s=180.,patient_locations={'P':'scene'})
    result=asyncio.run(coord.schedule_complete(authority.request('schedule'),plan,RecordedFixedProvider('P',tmp_path),FakeEtaProvider({})))
    if case=='no_resource':
        assert not result.allocated and rt.session.treatments==0
        return
    assert result.allocated and result.resource_result.outcome=='SATISFIED'
    assert json.loads((tmp_path/'agent_received_plan.json').read_text())==plan.model_dump(mode='json')
    authority.task_id=result.task.task_id
    context=rt.build_context()
    record=bridge.execute(plan,request_id='exec',context_ref=context.context_ref)
    assert record['actions'][0]['accepted'] and rt.session.treatments==1
    rt.advance(1);authority.finish(rt.query('exec'))
    assert manager.get_snapshot('r')['resources']['medic']['available_qty']==1
    assert len(api['requests'])==1


def test_offline_no_api_native_and_no_directory_reuse(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('offline called live dependency')
    monkeypatch.setattr(provider,'OpenAI',forbidden)
    monkeypatch.setattr('core301.research_runtime.m3a_runner.native_run',forbidden)
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'experiments/results') as root:
        directory,summary=asyncio.run(run('offline_test','test',root))
        assert not summary['real_llm'] and not summary['real_pulse']
        with pytest.raises(FileExistsError):asyncio.run(run('offline_test','test',root))


def test_missing_config_exports_blocked_before_pulse(monkeypatch,tmp_path):
    monkeypatch.setattr(provider,'PROJECT_ROOT',tmp_path)
    for key in ('OPENAI_BASE_URL','OPENAI_API_KEY','OPENAI_MODEL'):monkeypatch.delenv(key,raising=False)
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'experiments/results') as root:
        directory,summary=asyncio.run(run('real_agent_native','blocked',root))
        assert summary['overall_status']=='M3A_PARTIAL' and summary['failure']['stage']=='preflight'
        assert not summary['real_pulse'] and not summary['llm_request_attempted']
        assert json.loads((directory/'native_action_results.json').read_text())==[]
        assert json.loads((directory/'evaluation_result.json').read_text())['computation_state']=='NOT_RUN'
        with pytest.raises(FileExistsError):asyncio.run(run('real_agent_native','blocked',root))
