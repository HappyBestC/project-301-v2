import asyncio
import copy
import json
from types import SimpleNamespace
import pytest
from core301.dispatch.minimal.api import build_input,load_config,load_cases,read,CONFIG,request_agent_schedule
from core301.dispatch.minimal.agent_run import run_agent
from core301.dispatch.minimal.validation import validate_schedule

@pytest.fixture
def data():
    r,m=load_config()
    return build_input(r,m,load_cases(),horizon_min=60),read(CONFIG/'example_schedule.json')

class ScriptedProvider:
    def __init__(self,responses):
        self._config=SimpleNamespace(model='mock')
        self.responses=iter(responses);self.calls=[]
    async def decide_resource_schedule(self,context,**options):
        self.calls.append(options)
        value=next(self.responses)
        if isinstance(value,Exception):raise value
        return {'schedule':value,'validation':validate_schedule(context,value),'raw_response':json.dumps(value)}

def test_conflict_feedback_then_success_is_not_execution(data,tmp_path):
    context,good=data;bad=copy.deepcopy(good);bad['operations'][4]['staff_ids']=['A-basic-1']
    provider=ScriptedProvider([bad,good]);before=copy.deepcopy(context)
    out=tmp_path/'run';summary=asyncio.run(run_agent(provider,context,out,max_attempts=2))
    assert len(provider.calls)==2
    assert 'RESOURCE_OVERLAP' in {x['code'] for x in provider.calls[1]['feedback']['conflicts']}
    assert provider.calls[1]['previous_response']==json.dumps(bad)
    assert summary['status']=='partial_schedule'
    assert not summary['resources_committed'] and not summary['treatment_executed']
    assert len(summary['not_selected_patient_ids'])==11 and context==before
    assert json.loads((out/'attempt_01/validation.json').read_text())['conflicts']
    assert json.loads((out/'schedule.json').read_text())==good

def test_attempt_limit_keeps_rejection_without_ledger(data,tmp_path):
    context,s=data;s['operations'][4]['staff_ids']=['A-basic-1'];provider=ScriptedProvider([s,s])
    out=tmp_path/'run';summary=asyncio.run(run_agent(provider,context,out,max_attempts=2))
    assert summary['status']=='conflicts_attempt_limit'
    assert not (out/'schedule.json').exists() and not (out/'occupancy.json').exists()
    assert (out/'last_candidate.json').exists()

def test_request_failure_is_sanitized(data,tmp_path):
    context,_=data;provider=ScriptedProvider([RuntimeError('private-key-not-for-log')])
    out=tmp_path/'run';summary=asyncio.run(run_agent(provider,context,out))
    assert summary['status']=='request_or_adapter_failed' and len(provider.calls)==1
    assert 'private-key-not-for-log' not in ''.join(p.read_text() for p in out.rglob('*.json'))

def test_unknown_parameters_do_not_trigger_retries(data,tmp_path):
    context,s=data
    for result in s['patient_results']:
        if result['status']=='unscheduled':
            result.update(reason_code='missing_parameters',reason='当前缺少连续支持的终止与交接参数，无法确定所需支持时段。')
    provider=ScriptedProvider([s]);summary=asyncio.run(run_agent(provider,context,tmp_path/'run'))
    assert len(provider.calls)==1 and 'UNSCHEDULED_PARAMETERS_UNCHECKED' in summary['unchecked_codes']

def test_refuse_overwrite_before_request(data,tmp_path):
    context,s=data;provider=ScriptedProvider([s]);out=tmp_path/'run';out.mkdir()
    with pytest.raises(FileExistsError):asyncio.run(run_agent(provider,context,out))
    assert provider.calls==[]

@pytest.mark.parametrize('content,code',[
    ('```json\n{}\n```','MODEL_JSON_INVALID'),
    ('','MODEL_JSON_INVALID'),
    ('{"operations": []}','SCHEMA_INVALID'),
    (json.dumps({'demonstration_only':True,'selections':{},'operations':[]}), 'SCHEMA_INVALID'),
])
def test_invalid_model_response_is_rejected_and_saved(data,tmp_path,monkeypatch,content,code):
    import openai
    context,_=data
    class Client:
        def __init__(self,**kw):self.chat=SimpleNamespace(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kw):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content),finish_reason='stop')])
    monkeypatch.setattr(openai,'AsyncOpenAI',Client)
    provider=SimpleNamespace(_config=SimpleNamespace(model='mock',base_url='https://mock.invalid',api_key='never-record-this'))
    result=asyncio.run(request_agent_schedule(provider,context,audit_dir=tmp_path/'attempt'))
    assert code in {i['code'] for i in result['validation']['conflicts']}
    assert (tmp_path/'attempt/response.txt').read_text()==content
    assert 'never-record-this' not in (tmp_path/'attempt/request_messages.json').read_text()
