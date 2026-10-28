import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
import pytest
from pydantic import ValidationError
from core301.dispatch.complete_contracts import (CompletePlan,CompleteDispatchInput,ACTION_TYPES,decode_dispatch_input,
    from_legacy_plan,to_legacy_plan,from_resource_plan)
from core301.dispatch.complete_demo import research_plan,research_input,run_demo
from core301.dispatch.shared_resources import SharedResourceManager,Request,ResourceChange,Execution,ReleaseEvidence
from core301.dispatch.shared_resources.catalog import Catalog
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.shared_demo import fixture_provider,fixture_input
from core301.dispatch.demo import demo_eta

C=Catalog()
SINGLES=list(C.singles)
COMPOSITES=list(C.composites)


class Harness:
    def __init__(self,scope='hemothorax',*,counts=None,clinical=False,disjoint=True):
        self.plans=[research_plan(scope,p,'r') for p in ('A','B')]
        if clinical:
            self.plans=[CompletePlan.model_validate({**p.model_dump(),'scope_kind':'clinical_design'}) for p in self.plans]
        self.m=SharedResourceManager()
        stock,locations=research_scene(counts if counts is not None else {k:2 for k in C.resources})
        self.m.create_run('r',stock,locations)
        self.c=SharedDispatchCoordinator(self.m)
        self.c.register_run('r',[research_input(p) for p in self.plans],at_s=45.,
            patient_locations={'A':'scene','B':'scene'},facility_locations={'FAC-001':'scene'},legacy_assets_disjoint=disjoint)
        self.n=45
    def req(self,p='A',action=None):
        self.n+=1
        return Request(run_id='r',patient_id=p,plan_id='plan-'+p,request_id=f'q{self.n}',idempotency_key=f'k{self.n}',
                       action_instance_id=action,at_s=float(self.n),expected_state_version=self.m.get_snapshot('r')['state_version'])
    async def schedule(self,p='A',*,req=None,plan=None,provider=None,mode='onsite'):
        return await self.c.schedule_complete(req or self.req(p),plan or self.plans[0 if p=='A' else 1],
                                             provider or fixture_provider(p,mode),demo_eta())
    def snap(self):
        s=self.m.get_snapshot('r')
        for r in s['resources'].values():
            assert r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty']==r['total_qty']
            assert r['available_qty']+r['reserved_qty']+r['in_use_qty']+r['unavailable_qty']==r['total_qty']
        return s


def codes(r): return {c.code for c in r.resource_result.conflicts}


@pytest.mark.parametrize('scope',SINGLES+COMPOSITES)
def test_complete_profile_roundtrip_agent_receives_all_actions_and_real_reserve(scope):
    h=Harness(scope); p=h.plans[0]
    assert CompletePlan.model_validate_json(p.model_dump_json())==p
    assert from_resource_plan('r',p.to_resource_plan())==p
    source=research_input(p)
    assert CompleteDispatchInput.model_validate_json(source.model_dump_json())==source
    received=[]
    class Capture:
        async def decide_dispatch_with_resources(self,source,query,view):
            received.append(source.treatment_plan)
            assert [r['action_type'] for r in view['research_requirements']]==[a.action_type for a in p.actions]
            assert not view['constraints']['unsupported_dispatch_actions']
            return await fixture_provider('A').decide_dispatch(source,query)
    r=asyncio.run(h.schedule(provider=Capture()))
    assert r.allocated and received==[p]
    s=h.snap()
    assert set(s['plans']['plan-A']['actions'])=={a.action_instance_id for a in p.actions}
    assert s['state_version']==1 and r.resource_result.allocation_ids
    assert h.c.dispatch_input('r','A').treatment_plan==p


def test_all_twelve_actions_and_transfusion_have_actual_allocation_coverage():
    covered={a.action_type for scope in SINGLES for a in research_plan(scope).actions}
    p=research_plan('external_hemorrhage','A','r',blood=True)
    assert [a.action_type for a in p.actions]==['control_external_bleeding','transfusion']
    h=Harness('external_hemorrhage')
    # Separate explicit source registration: no upstream plan substitution.
    m=SharedResourceManager(); stock,locations=research_scene({k:2 for k in C.resources});m.create_run('r',stock,locations)
    coord=SharedDispatchCoordinator(m);coord.register_run('r',[research_input(p)],at_s=45.,patient_locations={'A':'scene'})
    r=asyncio.run(coord.schedule_complete(h.req(),p,fixture_provider('A'),demo_eta()))
    assert r.allocated
    covered.update(a.action_type for a in p.actions)
    assert covered==set(ACTION_TYPES)==set(C.requirements)


@pytest.mark.parametrize('scope',COMPOSITES)
def test_composite_last_resource_missing_rejects_entire_plan(scope):
    p=research_plan(scope); demand=C.requirements[p.actions[-1].action_type]
    missing=(demand.stock or demand.holds)[-1][0]
    counts={k:2 for k in C.resources};counts[missing]=0
    h=Harness(scope,counts=counts);before=h.snap()
    r=asyncio.run(h.schedule(mode='evacuation'))
    assert not r.allocated and 'RESOURCE_SHORTAGE' in codes(r) and h.snap()==before
    source=h.c.dispatch_input('r','A')
    assert source.ambulances[0].active_task_id is None and not source.facilities[0].reserved_patient_ids


@pytest.mark.parametrize('change',['reorder','side','parameter','missing_dependency','duplicate_id','albuterol','unknown_action','version','scope','conflict'])
def test_invalid_semantics_return_structured_failure_without_reserve(change):
    h=Harness();p=h.plans[0].model_dump();req=h.req()
    if change=='reorder': p['actions']=tuple(reversed(p['actions']))
    elif change=='side': p['actions'][1]['side']='Right'
    elif change=='parameter': p['actions'][1]['flow_ml_min']=999
    elif change=='missing_dependency': p['actions'][1]['depends_on']=()
    elif change=='duplicate_id': p['actions'][1]['action_instance_id']=p['actions'][0]['action_instance_id']
    elif change=='albuterol': p['actions'][1]['action_type']='inhaled_albuterol'
    elif change=='unknown_action': p['actions'][1]['action_type']='invented'
    elif change=='version': p['schema_version']='future'
    elif change=='scope': p['scope_id']='unverified'
    elif change=='conflict':
        p=research_plan('external_hemorrhage','A','r').model_dump()
        a=dict(p['actions'][-1],action_instance_id='extra',action_type='transfusion',depends_on=(p['actions'][-1]['action_instance_id'],))
        p['actions']=(*p['actions'],a)
    result=asyncio.run(h.c.schedule_complete(req,p,fixture_provider('A'),demo_eta()))
    assert not result.allocated and result.resource_result.conflicts and not h.snap()['allocations']
    if change=='version': assert 'CONTRACT_VERSION_UNSUPPORTED' in codes(result)
    if change=='scope': assert result.resource_result.outcome=='INDETERMINATE'


def test_reordered_sequence_with_repaired_ids_still_rejected_by_existing_rules():
    for scope in ('hemothorax','respiratory_muscle_impairment','external_hemorrhage',COMPOSITES[0]):
        p=research_plan(scope).to_resource_plan()
        p=p.model_copy(update={'actions':tuple(reversed(p.actions))})
        with pytest.raises(ValidationError): from_resource_plan('complete-demo',p)


def test_explicit_legacy_bridge_and_lossy_downgrade_refused():
    old=fixture_input('A','r')
    new=from_legacy_plan('r',old.treatment_plan,plan_id='plan-A',action_instance_ids=['A-0','A-1'],
         scope_kind='research_fixture',scope_id='respiratory_muscle_impairment',severity=.4,location_id='scene')
    assert new==research_plan('respiratory_muscle_impairment','A','r')
    assert decode_dispatch_input(old)==old
    assert decode_dispatch_input(research_input(new)).treatment_plan==new
    with pytest.raises(ValueError,match='LOSSY_CONVERSION'): to_legacy_plan(new)
    with pytest.raises(ValueError,match='CONTRACT_VERSION_UNSUPPORTED'):
        decode_dispatch_input({**old.model_dump(),'schema_version':'unknown'})


def test_clinical_unknown_and_unsafe_asset_identity_remain_blocked():
    h=Harness(clinical=True)
    assert asyncio.run(h.schedule()).resource_result.outcome=='INDETERMINATE'
    h=Harness(disjoint=None)
    assert asyncio.run(h.schedule(mode='team_response')).resource_result.outcome=='INDETERMINATE'
    assert not h.snap()['allocations']


def test_competition_idempotency_cancel_and_retry():
    h=Harness(counts={k:1 for k in C.resources});req=h.req()
    a=asyncio.run(h.schedule(req=req));assert a.allocated
    assert asyncio.run(h.schedule(req=req))==a
    assert not asyncio.run(h.schedule('B')).allocated
    r=h.c.lifecycle(h.req(),a.task.task_id,'cancel',detail='fixture')
    assert r.resource_result.outcome=='SATISFIED'
    assert asyncio.run(h.schedule('B')).allocated
    h.snap()


def test_threaded_complete_plans_do_not_overallocate():
    h=Harness(counts={k:1 for k in C.resources}); barrier=Barrier(2)
    class Race:
        def __init__(self,p):self.p=p
        async def decide_dispatch_with_resources(self,source,query,view):
            barrier.wait(timeout=10)
            return await fixture_provider(self.p).decide_dispatch(source,query)
    reqs=[h.req(p).model_copy(update={'at_s':50.}) for p in ('A','B')]
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(asyncio.run,h.schedule(p,req=req,provider=Race(p))) for p,req in zip(('A','B'),reqs)]
        results=[f.result() for f in futures]
    assert sum(r.allocated for r in results)==1 and len(h.snap()['plans'])==1


def test_resource_change_during_full_plan_decision_is_rechecked():
    h=Harness()
    class Change:
        async def decide_dispatch_with_resources(self,source,query,view):
            h.m.record_resource_change(h.req(),ResourceChange(resource_id='chest_tube_kit',kind='unavailable',reason='fixture',receipt_ref='fixture:fault'))
            return await fixture_provider('A').decide_dispatch(source,query)
    result=asyncio.run(h.schedule(provider=Change()))
    assert 'STALE_SNAPSHOT' in codes(result) and not h.snap()['allocations']


def test_unknown_execution_isolated_and_consumption_not_rolled_back():
    h=Harness();a=asyncio.run(h.schedule());p=h.plans[0]
    first=p.actions[0].action_instance_id
    assert h.c.begin_usage(h.req(action=first),a.task.task_id).outcome=='SATISFIED'
    assert h.m.record_execution(h.req(action=first),Execution(status='accepted',receipt_ref='fixture:control')).outcome=='SATISFIED'
    evidence=ReleaseEvidence(receipt_ref='fixture:stop',stopped=True,detached=True,cleared_for_reuse=True)
    assert h.m.release_usage(h.req(action=first),evidence).outcome=='SATISFIED'
    second=p.actions[1].action_instance_id
    assert h.c.begin_usage(h.req(action=second),a.task.task_id).outcome=='SATISFIED'
    amounts={k:v['quantity'] for k,v in h.snap()['allocations'].items() if v['resource_id']=='chest_tube_kit'}
    assert h.m.record_consumption(h.req(action=second),amounts=amounts,receipt_ref='fixture:opened').outcome=='SATISFIED'
    h.m.record_execution(h.req(action=second),Execution(status='unknown',receipt_ref='fixture:lost'))
    result=h.c.lifecycle(h.req(),a.task.task_id,'fail',detail='fixture')
    assert 'EXECUTION_UNCERTAIN' in codes(result)
    assert h.snap()['resources']['chest_tube_kit']['consumed_qty']==1
    assert h.snap()['resources']['medic']['unavailable_qty']==1


def test_provider_cannot_modify_original_complete_plan():
    h=Harness();original=h.plans[0]
    class Mutate:
        async def decide_dispatch_with_resources(self,source,query,view):
            object.__setattr__(source.treatment_plan,'actions',())
            return fixture_provider('A').proposal
    r=asyncio.run(h.schedule(provider=Mutate()))
    assert r.allocated and h.c.dispatch_input('r','A').treatment_plan==original
    assert len(h.snap()['plans']['plan-A']['actions'])==len(original.actions)


def test_demo_uses_nonlegacy_actions_and_real_state(capsys):
    records=asyncio.run(run_demo());capsys.readouterr()
    assert records[0]['result']['allocated'] and not records[1]['result']['allocated']
    for record in records:
        assert record['input_plan']==record['agent_received_plan']
        assert [a['action_type'] for a in record['input_plan']['actions']]==['occlusive_dressing','control_hemothorax_bleeding','chest_tube']
    assert records[0]['before']['state_version']==0 and records[0]['after']['state_version']==1


@pytest.mark.parametrize('mode',['onsite','team_response','evacuation'])
def test_complete_legacy_assets_and_cancellation_use_existing_lifecycle(mode):
    h=Harness();a=asyncio.run(h.schedule(mode=mode));assert a.allocated
    s=h.c.dispatch_input('r','B')
    if mode=='team_response': assert s.medical_teams[0].active_task_id==a.task.task_id
    if mode=='evacuation':
        assert s.ambulances[0].active_task_id==a.task.task_id and s.facilities[0].reserved_patient_ids==['A']
    if mode=='onsite':
        assert h.c.lifecycle(h.req(),a.task.task_id,'confirm_onsite').resource_result.outcome=='SATISFIED'
        result=h.c.lifecycle(h.req(),a.task.task_id,'end_episode')
    else: result=h.c.lifecycle(h.req(),a.task.task_id,'cancel',detail='fixture')
    assert result.resource_result.outcome=='SATISFIED'
    assert all(r['reserved_qty']==0 for r in h.snap()['resources'].values())
    s=h.c.dispatch_input('r','B')
    assert s.ambulances[0].active_task_id is None and s.medical_teams[0].active_task_id is None
    assert not s.facilities[0].reserved_patient_ids


def test_old_and_complete_plans_in_same_run_compete_in_one_ledger():
    from core301.dispatch.shared_demo import fixture_plan
    old=fixture_input('A','r');newplan=research_plan('hemothorax','B','r')
    data=research_input(newplan).model_dump()
    for key in ('facilities','ambulances','medical_teams'): data[key]=old.model_dump()[key]
    new=CompleteDispatchInput.model_validate(data)
    m=SharedResourceManager();stock,locations=research_scene({k:1 for k in C.resources});m.create_run('r',stock,locations)
    coord=SharedDispatchCoordinator(m)
    coord.register_run('r',[old,new],at_s=45.,patient_locations={'A':'scene','B':'scene'})
    def req(patient,time):
        return Request(run_id='r',patient_id=patient,plan_id='plan-'+patient,request_id=patient,idempotency_key=patient,
            at_s=time,action_instance_id=None,expected_state_version=m.get_snapshot('r')['state_version'])
    a=asyncio.run(coord.schedule(req('A',46.),fixture_plan('A'),fixture_provider('A'),demo_eta()))
    b=asyncio.run(coord.schedule_complete(req('B',47.),newplan,fixture_provider('B'),demo_eta()))
    assert a.allocated and not b.allocated and 'RESOURCE_IN_USE' in codes(b)
    assert len(m.get_snapshot('r')['plans'])==1


def test_real_llm_provider_sends_complete_contract_via_offline_http_mock(monkeypatch,tmp_path):
    import httpx,openai
    from core301.dispatch import providers
    monkeypatch.setattr(providers,'PROJECT_ROOT',tmp_path)
    for k,v in {'OPENAI_BASE_URL':'https://mock.invalid/v1','OPENAI_API_KEY':'offline-only','OPENAI_MODEL':'mock'}.items(): monkeypatch.setenv(k,v)
    h=Harness(COMPOSITES[0]);received=[]
    def respond(request):
        body=json.loads(request.content);data=json.loads(body['messages'][1]['content']);received.append(data)
        assert 'M2-C' in body['messages'][0]['content']
        assert data['treatment_plan']==h.plans[0].model_dump(mode='json')
        assert len(data['shared_resources']['research_requirements'])==3
        return httpx.Response(200,json={'id':'mock','object':'chat.completion','created':0,'model':'mock',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(fixture_provider('A').proposal.model_dump())}}]})
    def client(**kwargs): return openai.AsyncOpenAI(**kwargs,http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(providers,'AsyncOpenAI',client)
    assert asyncio.run(h.schedule(provider=providers.LLMDispatchProvider())).allocated
    assert len(received)==1
