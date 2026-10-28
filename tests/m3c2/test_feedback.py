from dataclasses import replace
import asyncio
import json
from types import SimpleNamespace
import httpx
import openai
import pytest
from core301.agent.resource_feedback import *
from core301.agent import feedback_provider as provider
from core301.research_runtime.m3c2_runner import FeedbackResearchRun,timing_preflight
from core301.research_runtime.m3c2_timing import DynamicTimingCaseRuntime,time_allowed,VERSION as TIMING_VERSION
from core301.research_runtime.bridge import executor_plan
from core301.runtime.v2.errors import V2Error
from core301.dispatch.shared_resources.models import Result,Conflict

@pytest.fixture
def host(tmp_path):
    h=FeedbackResearchRun(tmp_path,'r','offline_test');h.initialize()
    asyncio.run(h.schedule('A'));h.blocked=asyncio.run(h.schedule('B'));h.execute('A')
    yield h
    h.export_close()

def data(h,trigger=None,result=None):return build_feedback(h,'B',result or h.blocked,decision_id='r-d',trigger=trigger)

def decision(f,kind='KEEP_PLAN_AND_WAIT'):
    return {**{k:getattr(f,k) for k in ('run_id','patient_id','plan_id','decision_id','global_simulation_time_s','resource_state_version')},
        'schema_version':'301.treatment.feedback.m3c2.1','decision_type':kind,'reasoning_summary':'fixture',
        'refusal_reason':'uncertain' if kind=='DEFER_INSUFFICIENT_EVIDENCE' else None}

def validate(d,f,**kw):return validate_decision(parse_decision(json.dumps(d)),f,current_version=kw.get('version',f.resource_state_version),current_time=kw.get('time',f.global_simulation_time_s))

@pytest.mark.parametrize('kind',['KEEP_PLAN_AND_WAIT','DEFER_INSUFFICIENT_EVIDENCE','STOP_UNEXECUTABLE'])
def test_legal_initial(host,kind):
    f,_=data(host);assert validate(decision(f,kind),f).decision_type==kind

@pytest.mark.parametrize('mutation',['json','duplicate','missing','extra','patient','plan','run','time','version','decision','params','revision','wrong_phase'])
def test_invalid_decisions(host,mutation):
    f,_=data(host);d=decision(f)
    if mutation=='json':raw='not JSON'
    elif mutation=='duplicate':raw='{"run_id":"r","run_id":"r"}'
    else:
        if mutation=='missing':d.pop('refusal_reason')
        if mutation=='extra':d['extra']=1
        if mutation in ('patient','plan','run','decision'):d[mutation+'_id']='wrong'
        if mutation=='time':d['global_simulation_time_s']=181.
        if mutation=='version':d['resource_state_version']+=1
        if mutation=='params':d['native_payload']={}
        if mutation=='revision':d['decision_type']='PROPOSE_REVISED_PLAN'
        if mutation=='wrong_phase':d['decision_type']='RECHECK_RESOURCES'
        raw=json.dumps(d)
    with pytest.raises(ValueError):validate_decision(parse_decision(raw),f,current_time=180.,current_version=f.resource_state_version)

@pytest.mark.parametrize('changed',[{'version':999},{'time':181.}])
def test_context_changed_during_call(host,changed):
    f,_=data(host)
    with pytest.raises(ValueError):validate(decision(f),f,**changed)

@pytest.mark.parametrize('code,allowed',[
    ('RESOURCE_IN_USE','KEEP_PLAN_AND_WAIT'),('RESOURCE_SHORTAGE','KEEP_PLAN_AND_WAIT'),
    ('STALE_SNAPSHOT','RECHECK_RESOURCES'),('CONSTRAINT_UNKNOWN','DEFER_INSUFFICIENT_EVIDENCE'),('EXECUTION_UNCERTAIN','STOP_UNEXECUTABLE')])
def test_structured_conflict_distinctions(host,code,allowed):
    # Synthetic backend-result contract coverage, never described as a live conflict.
    original=host.blocked.resource_result
    c=original.conflicts[0].model_copy(update={'code':code})
    result=SimpleNamespace(resource_result=original.model_copy(update={'conflicts':(c,)}))
    f,p=data(host,result=result)
    assert f.conflict_codes==[code] and allowed in f.allowed_operations
    if code=='EXECUTION_UNCERTAIN':assert f.unresolved_execution and 'RECHECK_RESOURCES' not in f.allowed_operations
    assert p['feedback']['m2_result']['conflicts'][0]['code']==code

def test_projection_privacy_and_actual_conflict(host):
    f,p=data(host)
    assert p['feedback']['m2_result']==host.blocked.resource_result.model_dump(mode='json')
    assert set(p['observation']['measurements'])==set(BASIC)
    assert not any(x in json.dumps(p).lower() for x in ['severity','diagnostic','formal_grade','expected_winner'])
    p['resource_snapshot']['resources']['medic']['available_qty']=100
    assert host.manager.get_snapshot('r')['resources']['medic']['available_qty']==0

@pytest.mark.parametrize('kind,state',[('KEEP_PLAN_AND_WAIT','WAITING_FEEDBACK_EVENT'),('DEFER_INSUFFICIENT_EVIDENCE','DEFERRED'),('STOP_UNEXECUTABLE','STOPPED_UNEXECUTABLE')])
def test_control_no_hidden_submission(host,kind,state):
    host.feedback_controller.provider=FixedFeedbackProvider([kind])
    before=len([e for e in host.events if e['kind']=='RESOURCE_REQUESTED'])
    asyncio.run(host.feedback_controller.decide('B',host.blocked))
    assert host.patients['B'].state==state and host.patients['B'].request_id is None
    assert len([e for e in host.events if e['kind']=='RESOURCE_REQUESTED'])==before
    with pytest.raises(RuntimeError,match='LIMIT'):asyncio.run(host.feedback_controller.decide('B',host.blocked))

@pytest.mark.parametrize('dynamic',[False,True])
def test_release_recheck_and_separate_timing(tmp_path,dynamic):
    h=FeedbackResearchRun(tmp_path,'r','offline_test',exploratory=dynamic)
    try:
        h.initialize();asyncio.run(h.schedule('A'));blocked=asyncio.run(h.schedule('B'));h.execute('A')
        asyncio.run(h.feedback_controller.decide('B',blocked))
        h.advance_to(181.);h.capture();release=h.release_confirmed('A')
        f,_=build_feedback(h,'B',blocked,decision_id='d',trigger=release['sequence'])
        assert f.resource_changed and 'RECHECK_RESOURCES' in f.allowed_operations
        asyncio.run(h.feedback_controller.decide('B',blocked,release['sequence']))
        assert bool(h.patients['B'].request_id)==dynamic
        requests=[e for e in h.events if e['kind']=='RESOURCE_REQUESTED']
        assert requests[1]['request']['idempotency_key']!=requests[2]['request']['idempotency_key']
        assert requests[2]['request']['expected_state_version']>requests[1]['request']['expected_state_version']
        if dynamic:
            h.advance_to(182.);h.release_confirmed('B')
            assert h.patients['B'].receipt['protocol_version']==TIMING_VERSION
        else:assert h.patients['B'].state=='TIME_PROTOCOL_BLOCKED'
        assert h.manager.get_snapshot('r')['resources']['medic']['available_qty']==1
        with pytest.raises(RuntimeError):asyncio.run(h.feedback_controller.decide('B',blocked,release['sequence']))
    finally:h.export_close()

@pytest.mark.parametrize('now',[179.,180.5,182.,480.,float('nan')])
def test_unlisted_times(now):assert not time_allowed(now,True)

def test_probe_admission_preserves_old_time(tmp_path):
    report=asyncio.run(timing_preflight(tmp_path));assert report['status']=='PASS' and all(report['checks'].values())

@pytest.mark.parametrize('change',['action','target','severity','injury','patient','source'])
def test_dynamic_preserves_scope_and_identity(tmp_path,change):
    h=FeedbackResearchRun(tmp_path,'r','offline_test',exploratory=True)
    try:
        h.initialize();p=h.patients['B'];source,=p.runtime.registry.sources();plan=executor_plan(p.plan)
        if change=='patient':
            wrong=plan.model_copy(update={'patient_id':'other'})
            with pytest.raises(V2Error):p.runtime.execute_plan(wrong,request_id='bad',context_ref=p.runtime.build_context().context_ref)
        elif change=='source':
            p.runtime.session.actions['Hemorrhage'][0]['Compartment']='Spleen'
            asyncio.run(h.schedule('B'))
            with pytest.raises(Exception):h.execute('B')
        else:
            if change=='action':plan=type(plan)(patient_id=plan.patient_id,actions=[{'action_type':'fluid_resuscitation'}])
            if change=='target':plan.actions[0].compartment='LeftLeg'
            if change=='severity':source=replace(source,initial_severity=.6)
            if change=='injury':source=replace(source,injury_type='abdominal_internal_hemorrhage')
            with pytest.raises(V2Error):p.runtime.validate_treatment_timing(plan,source,181.)
        assert not any(x['phase']=='treatment' for x in p.runtime.session.action_results)
    finally:h.export_close()

def test_unknown_no_release_no_retry(tmp_path):
    h=FeedbackResearchRun(tmp_path,'r','offline_test',exploratory=True,faults={'B':{'unknown':True}})
    try:
        h.initialize();asyncio.run(h.schedule('B'))
        with pytest.raises(Exception):h.execute('B')
        h.cancel_unused('B','stop')
        assert any(a['status']=='QUARANTINED' for a in h.manager.get_snapshot('r')['allocations'].values())
        with pytest.raises(RuntimeError):h.execute('B')
    finally:h.export_close()

@pytest.mark.parametrize('failure',['timeout','invalid'])
def test_provider_failure_no_fixed_fallback(host,failure):
    def fail(*args):
        if failure=='timeout':raise TimeoutError('private')
        return 'invalid'
    host.feedback_controller.provider=SimpleNamespace(create_decision=fail)
    with pytest.raises(Exception):asyncio.run(host.feedback_controller.decide('B',host.blocked))
    assert host.patients['B'].request_id is None and host.feedback_controller.decisions==[]

@pytest.fixture
def api(monkeypatch,tmp_path):
    monkeypatch.setattr(provider,'PROJECT_ROOT',tmp_path)
    for k,v in {'OPENAI_BASE_URL':'https://mock.invalid/v1','OPENAI_API_KEY':'secret-test-key','OPENAI_MODEL':'mock-model'}.items():monkeypatch.setenv(k,v)
    state={'calls':0,'error':False,'timeout':False}
    def respond(request):
        state['calls']+=1
        if state['timeout']:raise httpx.ReadTimeout('secret-test-key',request=request)
        if state['error']:return httpx.Response(503,json={'error':{'message':'secret-test-key'}})
        return httpx.Response(200,json={'id':'mock','object':'chat.completion','created':0,'model':'mock-model','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],'usage':None})
    def client(**kw):
        assert kw['max_retries']==0 and kw['timeout']==60
        return openai.OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(provider,'OpenAI',client);return state

def test_http_budget_and_usage_null(api,tmp_path):
    p=provider.LLMTreatmentFeedbackProvider();payload={'feedback':{'decision_id':'d'}}
    assert p.create_decision(payload,tmp_path)=='{}';p.create_decision(payload,tmp_path)
    with pytest.raises(RuntimeError,match='LIMIT'):p.create_decision(payload,tmp_path)
    assert api['calls']==2
    responses=[json.loads(x) for x in (tmp_path/'llm_responses.jsonl').read_text().splitlines()]
    assert all(r['response']['usage'] is None for r in responses)
    assert 'secret-test-key' not in ''.join(f.read_text() for f in tmp_path.iterdir())

def test_input_budget_rejects_before_call(api,tmp_path):
    p=provider.LLMTreatmentFeedbackProvider()
    with pytest.raises(RuntimeError,match='BUDGET'):p.create_decision({'feedback':{'decision_id':'d'},'too_large':'x'*24000},tmp_path)
    assert api['calls']==0

@pytest.mark.parametrize('failure',['error','timeout'])
def test_http_no_retry_error_redaction(api,tmp_path,failure):
    api[failure]=True
    with pytest.raises(RuntimeError):provider.LLMTreatmentFeedbackProvider().create_decision({'feedback':{'decision_id':'d'}},tmp_path)
    assert api['calls']==1
    assert 'secret-test-key' not in ''.join(f.read_text() for f in tmp_path.iterdir())
