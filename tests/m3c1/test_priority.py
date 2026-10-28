import asyncio
import json
from types import SimpleNamespace
import httpx
import openai
import pytest
from core301.agent.priority_decision import *
from core301.agent import priority_provider as provider
from core301.research_runtime.m3c1_runner import PriorityResearchRun
from core301.research_runtime.m3c1_verify import verify
from core301.pulse.observation_projector import BASIC

PAYLOAD={'run_id':'r','simulation_time_s':180.,'resource_state_version':0,'patients':[{'patient_id':'r-A'},{'patient_id':'r-B'}]}

def draft(order=None,**kwargs):
    return dict(schema_version=VERSION,run_id='r',simulation_time_s=180.,resource_state_version=0,
        decision_type='prioritize',ordered_patient_ids=order or ['r-A','r-B'],reasoning_summary='test',refusal_reason=None,**kwargs)

def admit(d,**kwargs):
    return validate_decision(parse_decision(json.dumps(d)),PAYLOAD,current_time=kwargs.get('time',180.),current_version=kwargs.get('version',0))

@pytest.mark.parametrize('order',[['r-A','r-B'],['r-B','r-A']])
def test_legal(order):assert admit(draft(order)).ordered_patient_ids==order

@pytest.mark.parametrize('order',[['r-A','r-A'],['r-A'],['r-A','other'],['r-A','r-B','other']])
def test_bad_ids(order):
    with pytest.raises(ValueError):admit(draft(order))

@pytest.mark.parametrize('key,value',[('dose',1),('inventory',{}),('allocation_id','x'),('simulation_time_s',181.),('resource_state_version',1),('run_id','wrong'),('ordered_patient_ids',[]),('reasoning_summary',None)])
def test_bad_fields(key,value):
    d=draft();d[key]=value
    with pytest.raises(ValueError):admit(d)

@pytest.mark.parametrize('raw',['not JSON','```json\n{}\n```','{"run_id":"r","run_id":"r"}'])
def test_bad_json(raw):
    with pytest.raises(ValueError):parse_decision(raw)

@pytest.mark.parametrize('kind',['defer','refuse'])
def test_refusal(kind):
    d=draft();d.update(decision_type=kind,ordered_patient_ids=[],refusal_reason='insufficient evidence')
    with pytest.raises(ValueError,match='MODEL_'):admit(d)

@pytest.mark.parametrize('change',[{'time':181.},{'version':1}])
def test_changed_context(change):
    with pytest.raises(ValueError):admit(draft(),**change)

@pytest.fixture
def host(tmp_path):
    h=PriorityResearchRun(tmp_path,'r','offline_test');h.initialize()
    yield h
    h.export_close()

def test_authorized_projection(host):
    payload=build_input(host)
    assert payload['resource_snapshot']==host.manager.get_snapshot('r')
    assert payload['patients'][0]['patient_id']!=payload['patients'][1]['patient_id']
    for item in payload['patients']:
        assert set(item['measurements'])==set(BASIC)
        assert all(set(m)=={'value','status','observed_at_s','unit'} for m in item['measurements'].values())
        assert item['plan_summary'][0]['required_resources']=={'medic':1}
    assert not any(x in json.dumps(payload).lower() for x in ['severity','diagnostic','grade','expected_winner'])
    payload['resource_snapshot']['resources']['medic']['available_qty']=999
    assert host.manager.get_snapshot('r')['resources']['medic']['available_qty']==1

@pytest.mark.parametrize('mode,selected',[('fixed_A_first','A'),('fixed_B_first','B')])
def test_full_reverse_execution(tmp_path,mode,selected):
    (tmp_path/'run_manifest.json').write_text(json.dumps({'mode':'offline_test','real_llm':False,'priority_mode':mode}))
    h=PriorityResearchRun(tmp_path,'r','offline_test',priority_mode=mode)
    try:asyncio.run(h.episode())
    finally:h.export_close()
    result=verify(tmp_path,require_native=False)
    assert result['selected_patient']==selected
    assert result['treatment_counts'][selected]==1
    assert result['conflict_code']=='RESOURCE_IN_USE'

@pytest.mark.parametrize('failure',['invalid','timeout','refusal','stale'])
def test_failed_decision_no_resource_or_treatment(host,failure):
    def decide(payload,directory):
        if failure=='timeout':raise TimeoutError('secret')
        if failure=='invalid':return 'bad'
        d=draft()
        if failure=='refusal':d.update(decision_type='refuse',ordered_patient_ids=[],refusal_reason='no evidence')
        if failure=='stale':d['resource_state_version']+=1
        return json.dumps(d)
    host.provider=SimpleNamespace(create_decision=decide)
    with pytest.raises(Exception):host.priority_order()
    assert not host.manager.get_snapshot('r')['allocations']
    assert all(not p.request_id for p in host.patients.values())

@pytest.fixture
def api(monkeypatch,tmp_path):
    monkeypatch.setattr(provider,'PROJECT_ROOT',tmp_path)
    for k,v in {'OPENAI_BASE_URL':'https://mock.invalid/v1','OPENAI_API_KEY':'private-test-secret','OPENAI_MODEL':'mock-model'}.items():monkeypatch.setenv(k,v)
    state={'calls':0,'status':200,'timeout':False}
    def respond(request):
        state['calls']+=1
        if state['timeout']:raise httpx.ReadTimeout('private-test-secret',request=request)
        if state['status']!=200:return httpx.Response(state['status'],json={'error':{'message':'private-test-secret'}})
        return httpx.Response(200,json={'id':'mock','object':'chat.completion','created':0,'model':'mock-model',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(draft())}}], 'usage':None})
    def client(**kwargs):
        assert kwargs['max_retries']==0 and kwargs['timeout']==60
        return openai.OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(provider,'OpenAI',client)
    return state

def test_http_once_usage_null_prompt_schema(api,tmp_path):
    p=provider.LLMPriorityDecisionProvider();assert admit(json.loads(p.create_decision(PAYLOAD,tmp_path)))
    with pytest.raises(RuntimeError):p.create_decision(PAYLOAD,tmp_path)
    assert api['calls']==1
    request=json.loads((tmp_path/'llm_request.json').read_text())
    assert request['prompt_version']=='m3c1.1' and request['prompt_sha256']==provider.PROMPT_SHA
    assert VERSION in request['parameters']['messages'][0]['content']
    assert json.loads((tmp_path/'llm_response.json').read_text())['response']['usage'] is None
    assert 'private-test-secret' not in ''.join(p.read_text() for p in tmp_path.iterdir())

@pytest.mark.parametrize('failure',['http','timeout'])
def test_http_error_redacted_no_retry(api,tmp_path,failure):
    api['status']=503 if failure=='http' else 200;api['timeout']=failure=='timeout'
    with pytest.raises(RuntimeError):provider.LLMPriorityDecisionProvider().create_decision(PAYLOAD,tmp_path)
    assert api['calls']==1
    assert 'private-test-secret' not in ''.join(p.read_text() for p in tmp_path.iterdir())

def test_missing_measurement_unit_and_future_guard():
    from core301.agent.complete_decision import agent_input
    from core301.pulse.observation_projector import ObservationProjector,Sample
    known=[{'injury_type':'external_hemorrhage','compartment':'RightLeg'}]
    obs=ObservationProjector().project('r-A',180,{'vitals.heart_rate':Sample(90,179)})
    item=agent_input(obs,'r-A',known)
    assert item['measurements']['vitals.heart_rate']['unit']=='1/min'
    assert item['measurements']['vitals.pulse_oximetry']==dict(value=None,status='unavailable',observed_at_s=None,unit='1')
    obs.vitals.heart_rate.observed_at_s=181.
    with pytest.raises(ValueError):agent_input(obs,'r-A',known)


def test_native_llm_forbidden_with_fake_observations():
    from core301.research_runtime.m3c1_runner import run
    with pytest.raises(ValueError,match='real patient'):asyncio.run(run(priority_mode='llm_priority'))
