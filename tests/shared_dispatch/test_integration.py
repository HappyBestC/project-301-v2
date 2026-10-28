"""M2-B offline integration at the existing provider/service boundary."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from copy import deepcopy

import pytest

from core301.dispatch.shared_demo import fixture_input, fixture_plan, fixture_provider, run_demo
from core301.dispatch.demo import demo_eta
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.shared_resources import (SharedResourceManager, Request, Execution, ReleaseEvidence,
                                               ResourceChange, Plan, Action)
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.models import DispatchInput, TaskEvent
from core301.dispatch.events import EventTransition
from core301.dispatch.validation import DispatchError


class FixturePolicy:
    """Only the existing tests' illustrative API04 policy, not a production rule."""
    def __call__(self,task,event,patient_position,facility_position):
        state={('assigned','departed'):'to_patient',('to_patient','arrived_at_patient'):'at_patient',
               ('at_patient','transport_started'):'transporting',('transporting','arrived_at_facility'):'at_facility'}.get((task.state,event.kind))
        if state is None:
            raise DispatchError('DISPATCH_FAILED','fixture invalid sequence')
        if event.kind in ('arrived_at_patient','transport_started') and event.position!=patient_position:
            raise DispatchError('DISPATCH_FAILED','fixture invalid patient position')
        if event.kind=='arrived_at_facility' and event.position!=facility_position:
            raise DispatchError('DISPATCH_FAILED','fixture invalid facility position')
        return EventTransition(state,task.mode=='team_response' and event.kind=='arrived_at_patient')


class Harness:
    def __init__(self, *, counts=None, location='scene', disjoint=True, unknown=False, policy=True):
        self.m=SharedResourceManager()
        stock,locations=research_scene(counts or {'medic':2,'airway_kit':2,'ventilator':1},location_id=location)
        if unknown:
            locations=[type(locations[0]).model_validate({**locations[0].model_dump(),'capabilities':None})]
        self.stock,self.locations=stock,locations
        self.c=SharedDispatchCoordinator(self.m)
        self.location=location
        self.disjoint,self.policy=disjoint,FixturePolicy() if policy else None
        self.n=45
        self.register('run')
    def register(self,run):
        self.m.create_run(run,self.stock,self.locations)
        self.c.register_run(run,[fixture_input(p,run) for p in ('A','B')],at_s=45.,
            patient_locations={'A':self.location,'B':self.location},
            facility_locations={'FAC-001':self.location,'FAC-002':self.location},
            legacy_assets_disjoint=self.disjoint,event_policy=self.policy)
    def req(self,p='A',action=None,run='run',**updates):
        self.n+=1
        return Request.model_validate(dict(run_id=run,patient_id=p,plan_id='plan-'+p,
            request_id=f'req-{self.n}',idempotency_key=f'key-{self.n}',action_instance_id=action,
            at_s=float(self.n),expected_state_version=self.m.get_snapshot(run)['state_version'],**updates))
    def plan(self,p='A'):
        return fixture_plan(p,self.location)
    async def schedule(self,p='A',mode='onsite',provider=None,req=None,plan=None,run='run'):
        return await self.c.schedule(req or self.req(p,run=run),plan or self.plan(p),provider or fixture_provider(p,mode),demo_eta())
    def snap(self,run='run'):
        s=self.m.get_snapshot(run)
        for r in s['resources'].values():
            assert r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty']==r['total_qty']
            assert sum(r[k] for k in ('available_qty','reserved_qty','in_use_qty','unavailable_qty'))==r['total_qty']
            assert all(r[k]>=0 for k in ('available_qty','reserved_qty','in_use_qty','unavailable_qty'))
        return s
    def life(self,task,operation,p='A',**kwargs):
        return self.c.lifecycle(self.req(p),task.task_id,operation,**kwargs)
    def event(self,task,kind,position,p='A'):
        req=self.req(p)
        event=TaskEvent(run_id='run',event_id='ev-'+str(self.n),task_id=task.task_id,kind=kind,
                       occurred_at_s=req.at_s,position=position)
        return self.c.lifecycle(req,task.task_id,'event',event=event)


def codes(result):
    return {c.code for c in result.resource_result.conflicts}


def test_success_shared_visibility_and_immutable_agent_view():
    h=Harness()
    a=asyncio.run(h.schedule())
    assert a.allocated and len(a.resource_result.allocation_ids)==3
    class Capture:
        async def decide_dispatch_with_resources(self,source,query,view):
            assert next(r for r in view['resources'] if r['resource_id']=='ventilator')['reserved_qty']==1
            assert view['state_version']==a.resource_result.state_version
            assert 'allocations' not in view and 'plans' not in view and 'severity' not in view
            view['resources'].clear()
            source.facilities.clear()
            return await fixture_provider('B').decide_dispatch(source,query)
    b=asyncio.run(h.schedule('B',provider=Capture()))
    assert not b.allocated and 'RESOURCE_IN_USE' in codes(b)
    conflict=next(c for c in b.resource_result.conflicts if c.resource_id=='ventilator')
    assert conflict.required_qty==1 and conflict.available_qty==0 and conflict.blocking_allocation_ids
    assert h.snap()['resources']['ventilator']['reserved_qty']==1
    assert len(h.c.dispatch_input('run','B').facilities)==2


@pytest.mark.parametrize('missing',['ventilator','medic','airway_kit'])
def test_group_shortage_never_partially_commits(missing):
    counts={'medic':2,'airway_kit':2,'ventilator':1}; counts[missing]=0
    h=Harness(counts=counts)
    before=h.snap()
    answer=asyncio.run(h.schedule(mode='evacuation'))
    assert not answer.allocated and 'RESOURCE_SHORTAGE' in codes(answer)
    assert h.snap()==before
    source=h.c.dispatch_input('run','A')
    assert source.ambulances[0].active_task_id is None
    assert not source.facilities[0].reserved_patient_ids


def test_thread_race_only_one_whole_dispatch_is_confirmed():
    h=Harness()
    barrier=Barrier(2)
    class Racing:
        def __init__(self,p): self.p=p
        async def decide_dispatch_with_resources(self,source,query,view):
            barrier.wait(timeout=10)
            return await fixture_provider(self.p).decide_dispatch(source,query)
    requests=[h.req(p) for p in ('A','B')]
    # Same simulation instant, neither contender loses merely because of time.
    requests=[r.model_copy(update={'at_s':50.}) for r in requests]
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(asyncio.run,h.schedule(p,req=req,provider=Racing(p))) for p,req in zip(('A','B'),requests)]
        answers=[f.result() for f in futures]
    assert sum(a.allocated for a in answers)==1
    loser=next(a for a in answers if not a.allocated)
    assert 'STALE_SNAPSHOT' in codes(loser)
    assert len(h.snap()['plans'])==1 and h.snap()['resources']['ventilator']['reserved_qty']==1


@pytest.mark.parametrize('kind',['fault','move'])
def test_state_changes_during_agent_decision_are_rechecked(kind):
    h=Harness()
    class Changes:
        async def decide_dispatch_with_resources(self,source,query,view):
            change=ResourceChange(resource_id='ventilator',kind=kind,reason='fixture',receipt_ref='fixture:change',
                                  location_id=None)
            assert h.m.record_resource_change(h.req(),change).outcome=='SATISFIED'
            return await fixture_provider('A').decide_dispatch(source,query)
    result=asyncio.run(h.schedule(provider=Changes()))
    assert not result.allocated and 'STALE_SNAPSHOT' in codes(result)
    assert not h.snap()['allocations']


@pytest.mark.parametrize('unknown',['clinical','capability'])
def test_unknown_is_not_success(unknown):
    h=Harness(unknown=unknown=='capability')
    plan=h.plan()
    if unknown=='clinical': plan=plan.model_copy(update={'scope_kind':'clinical_design'})
    answer=asyncio.run(h.schedule(plan=plan))
    assert answer.resource_result.outcome=='INDETERMINATE' and not answer.allocated
    assert not h.snap()['allocations']


@pytest.mark.parametrize('disjoint',[None,False])
@pytest.mark.parametrize('mode',['team_response','evacuation'])
def test_unknown_or_overlapping_ownership_fails_closed(disjoint,mode):
    h=Harness(disjoint=disjoint)
    answer=asyncio.run(h.schedule(mode=mode))
    assert answer.resource_result.outcome=='INDETERMINATE' and 'CONSTRAINT_UNKNOWN' in codes(answer)
    assert not h.snap()['allocations']


@pytest.mark.parametrize('mode',['onsite','team_response','evacuation'])
def test_cancel_releases_both_unstarted_ledgers_and_duplicate_does_not_repeat(mode):
    h=Harness()
    a=asyncio.run(h.schedule(mode=mode))
    assert a.allocated
    req=h.req()
    cancel=h.c.lifecycle(req,a.task.task_id,'cancel',detail='fixture cancellation')
    assert cancel.resource_result.outcome=='SATISFIED'
    s=h.snap()
    assert h.c.lifecycle(req,a.task.task_id,'cancel',detail='fixture cancellation')==cancel
    assert h.snap()==s
    source=h.c.dispatch_input('run','B')
    assert source.ambulances[0].active_task_id is None and source.medical_teams[0].active_task_id is None
    assert not source.facilities[0].reserved_patient_ids
    assert asyncio.run(h.schedule('B',mode=mode)).allocated


def test_same_request_and_changed_key_never_duplicate_tasks():
    h=Harness(); req=h.req()
    first=asyncio.run(h.schedule(req=req)); before=h.snap()
    assert asyncio.run(h.schedule(req=req))==first
    assert h.snap()==before
    changed=req.model_copy(update={'at_s':99.})
    assert 'IDEMPOTENCY_CONFLICT' in codes(asyncio.run(h.schedule(req=changed)))
    changed=req.model_copy(update={'idempotency_key':'new-key','expected_state_version':before['state_version']})
    assert 'IDEMPOTENCY_CONFLICT' in codes(asyncio.run(h.schedule(req=changed)))
    assert 'IDEMPOTENCY_CONFLICT' in codes(h.c.lifecycle(req,first.task.task_id,'cancel'))
    assert h.snap()==before


def test_inflight_duplicate_is_not_a_second_agent_call():
    h=Harness(); req=h.req()
    async def run():
        started,finish=asyncio.Event(),asyncio.Event()
        class Waiting:
            async def decide_dispatch_with_resources(self,source,query,view):
                started.set(); await finish.wait()
                return await fixture_provider('A').decide_dispatch(source,query)
        pending=asyncio.create_task(h.schedule(req=req,provider=Waiting()))
        await started.wait()
        duplicate=await h.schedule(req=req)
        assert 'REQUEST_IN_PROGRESS' in codes(duplicate) and not duplicate.allocated
        finish.set()
        assert (await pending).allocated
    asyncio.run(run())
    assert len(h.snap()['plans'])==1


def test_runs_are_isolated():
    h=Harness(); h.register('other')
    assert asyncio.run(h.schedule()).allocated
    assert asyncio.run(h.schedule(run='other')).allocated
    assert h.snap('run')['resources']['ventilator']['reserved_qty']==1
    assert h.snap('other')['resources']['ventilator']['reserved_qty']==1


@pytest.mark.parametrize('mode',['team_response','evacuation'])
def test_legacy_unique_asset_is_shared_and_failure_does_not_reserve_medical(mode):
    h=Harness(counts={'medic':4,'airway_kit':4,'ventilator':2})
    assert asyncio.run(h.schedule(mode=mode)).allocated
    before=h.snap()
    b=asyncio.run(h.schedule('B',mode=mode))
    assert not b.allocated
    assert h.snap()==before
    source=h.c.dispatch_input('run','B')
    asset=source.medical_teams[0] if mode=='team_response' else source.ambulances[0]
    assert asset.active_task_id is not None


def test_facility_capacity_failure_has_no_medical_or_ambulance_leak():
    h=Harness()
    # New setup with an explicitly full zero-capacity facility.
    h.m.create_run('full',h.stock,h.locations)
    sources=[fixture_input(p,'full').model_dump() for p in ('A','B')]
    for s in sources: s['facilities'][0]['capacity']=0
    h.c.register_run('full',sources,at_s=45.,patient_locations={'A':'scene','B':'scene'},
                     facility_locations={'FAC-001':'scene'},legacy_assets_disjoint=True)
    before=h.snap('full')
    a=asyncio.run(h.schedule(mode='evacuation',run='full'))
    assert not a.allocated and h.snap('full')==before
    assert h.c.dispatch_input('full','B').ambulances[0].active_task_id is None


def test_evacuation_events_readiness_admission_and_episode_release():
    h=Harness(location='hospital')
    a=asyncio.run(h.schedule(mode='evacuation')); assert a.allocated
    assert h.c.begin_usage(h.req(action='A-int'),a.task.task_id).outcome!='SATISFIED'
    source=h.c.dispatch_input('run','A')
    for kind,pos in [('departed',source.ambulances[0].position),('arrived_at_patient',source.position),
                     ('transport_started',source.position),('arrived_at_facility',source.facilities[0].position)]:
        e=h.event(a.task,kind,pos)
        assert e.resource_result.outcome=='SATISFIED'
    # ETA or arrival alone never authorizes treatment / returns capacity.
    assert h.c.begin_usage(h.req(action='A-int'),a.task.task_id).outcome!='SATISFIED'
    assert h.life(a.task,'admit').resource_result.outcome=='SATISFIED'
    source=h.c.dispatch_input('run','B')
    assert source.facilities[0].admitted_patient_ids==['A']
    assert source.ambulances[0].active_task_id is None
    assert h.life(a.task,'end_episode').resource_result.outcome=='SATISFIED'
    assert not h.c.dispatch_input('run','B').facilities[0].admitted_patient_ids
    assert h.snap()['resources']['ventilator']['available_qty']==1


def test_team_arrival_readiness_and_explicit_end():
    h=Harness()
    a=asyncio.run(h.schedule(mode='team_response')); assert a.allocated
    source=h.c.dispatch_input('run','A')
    assert h.c.begin_usage(h.req(action='A-int'),a.task.task_id).outcome!='SATISFIED'
    assert h.event(a.task,'departed',source.medical_teams[0].position).resource_result.outcome=='SATISFIED'
    assert h.event(a.task,'arrived_at_patient',source.position).task.treatment_ready_at_s is not None
    assert h.life(a.task,'end_episode').resource_result.outcome=='SATISFIED'
    assert h.c.dispatch_input('run','B').medical_teams[0].active_task_id is None


def test_event_without_policy_is_rejected_without_state_change():
    h=Harness(policy=False)
    a=asyncio.run(h.schedule(mode='team_response')); before=h.snap()
    e=h.event(a.task,'departed',h.c.dispatch_input('run','A').medical_teams[0].position)
    assert not e.task and e.resource_result.outcome=='UNSATISFIED' and h.snap()==before


@pytest.mark.parametrize('execution',['unknown','rejected','accepted'])
def test_active_medical_resources_block_legacy_release_and_consumption_never_rolls_back(execution):
    h=Harness(); a=asyncio.run(h.schedule())
    assert h.c.begin_usage(h.req(action='A-int'),a.task.task_id).outcome=='SATISFIED'
    amounts={k:v['quantity'] for k,v in h.snap()['allocations'].items() if v['resource_id']=='airway_kit'}
    assert h.m.record_consumption(h.req(action='A-int'),amounts=amounts,receipt_ref='fixture:opened').outcome=='SATISFIED'
    assert h.m.record_execution(h.req(action='A-int'),Execution(status=execution,receipt_ref='fixture:receipt')).outcome=='SATISFIED'
    before=h.snap()
    assert 'EXECUTION_UNCERTAIN' in codes(h.life(a.task,'fail',detail='fixture failure'))
    assert h.snap()==before and h.snap()['resources']['airway_kit']['consumed_qty']==1
    if execution!='unknown':
        evidence=ReleaseEvidence(receipt_ref='fixture:stopped',stopped=True,detached=True,cleared_for_reuse=True)
        assert h.m.release_usage(h.req(action='A-int'),evidence).outcome=='SATISFIED'
        assert h.life(a.task,'fail',detail='fixture failure').resource_result.outcome=='SATISFIED'
        assert h.snap()['resources']['airway_kit']['total_qty']==1
        assert h.snap()['resources']['ventilator']['available_qty']==1


@pytest.mark.parametrize('action',['control_external_bleeding','control_hemothorax_bleeding','control_internal_bleeding','remove_from_exposure','inhaled_albuterol'])
def test_unsupported_actions_are_not_dropped(action):
    h=Harness()
    p=h.plan().model_copy(update={'actions':(Action(action_instance_id='unsupported',action_type=action),)})
    a=asyncio.run(h.schedule(plan=p))
    assert 'ACTION_CONTRACT_UNSUPPORTED' in codes(a) and not h.snap()['allocations']


def test_cannot_rewrite_upstream_plan_or_location():
    h=Harness()
    p=h.plan().model_copy(update={'actions':h.plan().actions[:1]})
    assert 'PLAN_MISMATCH' in codes(asyncio.run(h.schedule(plan=p)))
    p=h.plan().model_copy(update={'location_id':'elsewhere'})
    assert 'LOCATION_MISMATCH' in codes(asyncio.run(h.schedule(plan=p)))
    assert not h.snap()['allocations']


def test_provider_without_shared_input_does_not_silently_fallback():
    h=Harness()
    class Old:
        async def decide_dispatch(self,*args): raise AssertionError('must not be called')
    answer=asyncio.run(h.schedule(provider=Old()))
    assert not answer.allocated and 'DISPATCH_FAILED' in codes(answer)
    assert not h.snap()['allocations']


def test_demo_real_state_and_conservation(capsys):
    records=asyncio.run(run_demo()); capsys.readouterr()
    assert records[1]['result']['allocated'] and not records[2]['result']['allocated']
    assert records[-2]['result']['allocated']
    assert records[-1]['snapshot']['resources']['ventilator']['available_qty']==1
    for record in records:
        for r in record['snapshot']['resources'].values():
            assert r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty']==r['total_qty']
            assert sum(r[k] for k in ('available_qty','reserved_qty','in_use_qty','unavailable_qty'))==r['total_qty']


def test_early_failure_is_idempotent_and_history_is_detached():
    h=Harness(); req=h.req()
    wrong=h.plan().model_copy(update={'location_id':'elsewhere'})
    a=asyncio.run(h.schedule(req=req,plan=wrong))
    assert not a.allocated
    assert 'IDEMPOTENCY_CONFLICT' in codes(asyncio.run(h.schedule(req=req)))
    history=h.c.get_history('run')
    assert history[0]['result']==a.model_dump(mode='json')
    history.clear()
    assert len(h.c.get_history('run'))==1


def test_impossible_agent_proposal_cannot_create_any_task():
    h=Harness()
    class Invented:
        async def decide_dispatch_with_resources(self,source,query,view):
            return {'patient_id':'A','mode':'team_response','team_id':'invented','ambulance_id':None,'target_facility_id':None}
    a=asyncio.run(h.schedule(provider=Invented()))
    assert not a.allocated and 'DISPATCH_FAILED' in codes(a)
    assert not h.snap()['allocations']


def test_reserve_failure_discards_already_validated_legacy_stage(monkeypatch):
    h=Harness()
    from core301.dispatch.shared_resources import Result
    def fail(request,plan):
        return Result(run_id=request.run_id,patient_id=request.patient_id,plan_id=request.plan_id,
                      request_id=request.request_id,state_version=0,outcome='UNSATISFIED')
    monkeypatch.setattr(h.m,'reserve',fail)
    a=asyncio.run(h.schedule(mode='evacuation'))
    assert not a.allocated
    assert a.legacy_state_version==0 and not h.snap()['allocations']
    s=h.c.dispatch_input('run','B')
    assert not s.facilities[0].reserved_patient_ids and s.ambulances[0].active_task_id is None


def test_same_canonical_asset_cannot_be_imported_in_both_ledgers():
    h=Harness()
    h.m.create_run('overlap',[r.model_copy(update={'resource_id':'TEAM-001'}) if r.resource_id=='medic' else r
                              for r in h.stock],h.locations)
    with pytest.raises(ValueError,match='both ledgers'):
        h.c.register_run('overlap',[fixture_input('A','overlap')],at_s=45.,patient_locations={'A':'scene'},
                         legacy_assets_disjoint=True)


def test_registration_never_overwrites_or_copies_different_legacy_inventory():
    h=Harness()
    with pytest.raises(ValueError,match='already registered'):
        h.c.register_run('run',[fixture_input('A','run')],at_s=45.,patient_locations={'A':'scene'})
    sources=[fixture_input(p,'different').model_dump() for p in ('A','B')]
    sources[1]['facilities'][0]['capacity']=9
    h.m.create_run('different',h.stock,h.locations)
    with pytest.raises(ValueError,match='same initial legacy'):
        h.c.register_run('different',sources,at_s=45.,patient_locations={'A':'scene','B':'scene'})


def test_llm_existing_entry_serializes_shared_view_and_sanitizes_output(monkeypatch,tmp_path):
    import json
    import httpx
    import openai
    from core301.dispatch import providers
    monkeypatch.setattr(providers,'PROJECT_ROOT',tmp_path)
    for key,value in {'OPENAI_BASE_URL':'https://mock.invalid/v1','OPENAI_API_KEY':'offline-test',
                      'OPENAI_MODEL':'offline-model'}.items():
        monkeypatch.setenv(key,value)
    requests=[]
    def respond(request):
        payload=json.loads(request.content); requests.append(payload)
        source=json.loads(payload['messages'][1]['content'])
        assert source['shared_resources']['resources']
        assert source['shared_resources']['research_requirements'][0]['action_type']=='intubation'
        assert source['shared_resources']['scope_kind']=='research_fixture'
        assert source['treatment_plan']==fixture_input('A','run').treatment_plan.model_dump()
        assert 'M2-B' in payload['messages'][0]['content']
        assert 'severity' not in source and 'call_id' not in source and 'context' not in source
        return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,'model':'offline-model',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant',
             'content':json.dumps(fixture_provider('A').proposal.model_dump())}}]})
    def client(**kwargs):
        return openai.AsyncOpenAI(**kwargs,http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(providers,'AsyncOpenAI',client)
    h=Harness()
    answer=asyncio.run(h.schedule(provider=providers.LLMDispatchProvider()))
    assert answer.allocated and len(requests)==1


def test_lifecycle_cannot_rewind_medical_time():
    h=Harness(); a=asyncio.run(h.schedule())
    req=h.req()
    assert h.m.record_resource_change(h.req(),ResourceChange(resource_id='ventilator',kind='fault',
                     reason='fixture',receipt_ref='fixture:fault')).outcome=='SATISFIED'
    req=req.model_copy(update={'expected_state_version':h.snap()['state_version']})
    answer=h.c.lifecycle(req,a.task.task_id,'confirm_onsite')
    assert not answer.task and 'DISPATCH_FAILED' in codes(answer)


def test_legacy_capability_contradiction_does_not_publish_medical_success():
    h=Harness()
    h.m.create_run('incapable',h.stock,h.locations)
    sources=[fixture_input(p,'incapable').model_dump() for p in ('A','B')]
    for s in sources: s['medical_teams'][0]['supported_action_types']=[]
    h.c.register_run('incapable',sources,at_s=45.,patient_locations={'A':'scene','B':'scene'},
                     legacy_assets_disjoint=True)
    before=h.snap('incapable')
    a=asyncio.run(h.schedule(mode='team_response',run='incapable'))
    assert not a.allocated and 'RESOURCE_UNAVAILABLE' in codes(a)
    assert h.snap('incapable')==before
    assert h.c.dispatch_input('incapable','B').medical_teams[0].active_task_id is None
