"""Offline central state machine and fault tests; no native/LLM evidence."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from core301.research_runtime.m3b_runner import MultiPatientResearchRun
from core301.research_runtime.pulse_worker import PulseWorkerSession,WorkerUncertain


@pytest.fixture
def host(tmp_path):
    h=MultiPatientResearchRun(tmp_path,'test','offline_test');h.initialize()
    yield h
    h.export_close()


def schedule(h,label,request=None):return asyncio.run(h.schedule(label,request))


def test_single_ledger_conflict_identity_and_new_request_recovery(host):
    h=host;a=schedule(h,'A');b=schedule(h,'B')
    assert a.allocated and not b.allocated
    conflict=b.resource_result.conflicts[0]
    assert conflict.code=='RESOURCE_IN_USE' and conflict.available_qty==0 and conflict.required_qty==1
    assert tuple(a.resource_result.allocation_ids)==conflict.blocking_allocation_ids
    assert h.patients['A'].authority.manager is h.patients['B'].authority.manager is h.manager
    assert len(h.manager.get_snapshot('test')['allocations'])==1
    with pytest.raises(ValueError):h.execute('B')
    assert not any(x['phase']=='treatment' for x in h.patients['B'].runtime.session.action_results)
    h.execute('A');h.advance_to(181.);h.capture();release=h.release_confirmed('A')
    snapshot=h.manager.get_snapshot('test');assert snapshot['resources']['medic']['available_qty']==1
    new=schedule(h,'B');assert new.allocated and new.resource_result.state_version>conflict.state_version
    assert not h.execute('B') and h.patients['B'].state=='TIME_PROTOCOL_BLOCKED'
    assert h.patients['B'].runtime.session.time==181.


def test_duplicate_schedule_same_allocation_and_execution_guard(host):
    req=host.patients['A'].authority.request('schedule')
    a=schedule(host,'A',req);b=schedule(host,'A',req)
    assert a==b and len(host.manager.get_snapshot('test')['allocations'])==1
    host.execute('A')
    with pytest.raises(ValueError,match='already submitted'):host.execute('A')
    assert sum(r['phase']=='treatment' for r in host.patients['A'].runtime.session.action_results)==1


def test_stale_resource_version_does_not_reserve(host):
    req=host.patients['B'].authority.request('schedule');schedule(host,'A')
    result=schedule(host,'B',req)
    assert result.resource_result.conflicts[0].code=='STALE_SNAPSHOT'
    assert len(host.manager.get_snapshot('test')['allocations'])==1


def test_failed_idempotency_key_does_not_turn_into_success(host):
    schedule(host,'A');req=host.patients['B'].authority.request('schedule');first=schedule(host,'B',req)
    host.execute('A');host.advance_to(181.);host.release_confirmed('A')
    assert schedule(host,'B',req)==first
    assert schedule(host,'B').allocated


@pytest.mark.parametrize('target',[179.,182.,481.,float('nan')])
def test_clock_rejects_backward_skip_endpoint_and_nan(host,target):
    with pytest.raises(ValueError):host.advance_to(target)
    assert host.times()=={'A':180.,'B':180.}


def test_wall_time_and_order_do_not_change_clock(host,monkeypatch):
    import time
    monkeypatch.setattr(time,'time',lambda:1e20)
    schedule(host,'A');schedule(host,'B')
    assert host.global_simulation_time_s==180. and host.times()=={'A':180.,'B':180.}
    kinds=[e['kind'] for e in host.events]
    assert kinds.index('RESOURCE_RESERVED')<kinds.index('RESOURCE_BLOCKED')<kinds.index('PATIENT_WAITING')


def test_acceptance_alone_cannot_release_or_cross_patient_finish(host):
    schedule(host,'A');host.execute('A')
    with pytest.raises(ValueError):host.release_confirmed('A')
    host.advance_to(181.)
    receipt=host.patients['A'].runtime.query(host.patients['A'].request_id)
    with pytest.raises(ValueError):host.patients['B'].authority.finish(receipt)
    assert host.manager.get_snapshot('test')['resources']['medic']['in_use_qty']==1


def test_cross_patient_plan_and_session_binding_rejected(host):
    a,b=host.patients.values();schedule(host,'A')
    with pytest.raises(ValueError):b.bridge.execute(a.plan,request_id='wrong',context_ref=b.runtime.build_context().context_ref)
    with pytest.raises(ValueError):b.runtime.session.bind_execution({'run_id':'test','patient_id':a.plan.patient_id})
    assert not any(x['phase']=='treatment' for x in b.runtime.session.action_results)


def test_early_and_late_treatment_blocked(host):
    schedule(host,'A')
    host.global_simulation_time_s=179.
    with pytest.raises(RuntimeError,match='CLOCK_DIVERGENCE'):host.execute('A')
    host.global_simulation_time_s=180.;host.advance_to(181.)
    assert host.execute('A') is False
    assert not any(x['phase']=='treatment' for x in host.patients['A'].runtime.session.action_results)


def test_unknown_quarantine_stops_replay_and_preserves_allocation(tmp_path):
    h=MultiPatientResearchRun(tmp_path,'unknown','offline_test',faults={'A':{'unknown':True}})
    try:
        h.initialize();schedule(h,'A');schedule(h,'B')
        with pytest.raises(Exception):h.execute('A')
        with pytest.raises(RuntimeError,match='HALTED'):h.execute('A')
        snap=h.manager.get_snapshot('unknown')
        assert snap['resources']['medic']['available_qty']==0
        assert any(v['status']=='QUARANTINED' for v in snap['allocations'].values())
    finally:h.export_close()
    assert h.summary['unresolved_allocations']


@pytest.mark.parametrize('fault',[{'initialize':True},{'advance_at':181.},{'drift':True}])
def test_worker_faults_abort_without_claiming_synchronized_progress(tmp_path,fault):
    h=MultiPatientResearchRun(tmp_path,'fault','offline_test',faults={'B':fault})
    try:
        if fault.get('advance_at'):
            h.initialize()
            with pytest.raises(RuntimeError):h.advance_to(181.)
            assert h.halted and h.global_simulation_time_s==180.
            assert h.patients['A'].runtime.session.time==181. and h.patients['B'].runtime.session.time==180.
            with pytest.raises(RuntimeError):schedule(h,'A')
        else:
            with pytest.raises(RuntimeError):h.initialize()
    finally:h.export_close()
    assert all(p.runtime.session.closed for p in h.patients.values())


def test_budget_is_execution_limit_not_medical_duration(tmp_path):
    h=MultiPatientResearchRun(tmp_path,'budget','offline_test',event_budget=1)
    try:
        with pytest.raises(RuntimeError,match='BUDGET'):h.initialize()
    finally:h.export_close()


@pytest.mark.parametrize('failure',['timeout','identity','interruption','native_exception'])
def test_worker_transport_uncertain_never_retries(tmp_path,failure):
    s=object.__new__(PulseWorkerSession)
    s.run_id='r';s.patient_id='P';s.sequence=0;s.time=180.;s.ready=True;s.uncertain=False;s.closed=False
    s.execution_identity=None;s.timeout=.01;s.directory=tmp_path;s.worker_pid=42;s.action_results=[]
    replies={'run_id':'r','patient_id':'P','command_id':1,'worker_pid':42,'ready':True,
             'action_results':[],'simulation_time_s':180.,'ok':True,'value':None}
    if failure=='identity':replies['patient_id']='Q'
    if failure=='native_exception':replies.update(ok=False,error_type='RuntimeError',error='injected')
    calls=[]
    def recv():
        if failure=='interruption':raise EOFError('worker died')
        return replies
    s.pipe=SimpleNamespace(send=lambda x:calls.append(x),poll=lambda _:failure!='timeout',recv=recv)
    with pytest.raises(WorkerUncertain):s.call('advance_time',1.)
    with pytest.raises(WorkerUncertain):s.call('advance_time',1.)
    assert s.uncertain and len(calls)==1


def test_complete_fake_episode_export_wait_and_no_fabricated_B_receipt(tmp_path):
    # The public runner supplies this manifest; this direct-host fixture must too.
    (tmp_path/'run_manifest.json').write_text(json.dumps({'mode':'offline_test','real_llm':False}))
    h=MultiPatientResearchRun(tmp_path,'full','offline_test')
    try:asyncio.run(h.episode())
    finally:h.export_close()
    assert h.summary['overall_status']=='M3B_IMPLEMENTED_NATIVE_UNVERIFIED'
    assert h.summary['waiting_status']=='WAITING_NOT_VERIFIED'
    assert h.summary['waiting_duration_s']==1. and not h.summary['unresolved_allocations']
    for p in h.patients.values():assert p.observations==301 and p.runtime.session.time==480.
    b=h.patients['B']
    assert not (b.directory/'execution_receipt.json').exists()
    rows=[json.loads(x) for x in (b.directory/'observations.jsonl').read_text().splitlines()]
    assert rows[0]['simulation_time_s']==180 and rows[1]['simulation_time_s']==181
    assert rows[1]['patient_state']=='WAITING_RESOURCE'
    assert h.manager.get_snapshot('full')['resources']['medic']['available_qty']==1
    from core301.research_runtime.m3b_verify import verify
    assert verify(tmp_path,require_native=False)['status']=='PASS_OFFLINE_ONLY'
    with pytest.raises(ValueError,match='Not native'):verify(tmp_path)
    with (b.directory/'observations.jsonl').open('a') as f:f.write('\n')
    with pytest.raises(ValueError,match='SHA mismatch'):verify(tmp_path,require_native=False)


def test_advance_failure_after_acceptance_preserves_unresolved_use(tmp_path):
    h=MultiPatientResearchRun(tmp_path,'abort','offline_test',faults={'B':{'advance_at':181.}})
    try:
        h.initialize();schedule(h,'A');schedule(h,'B');h.execute('A')
        with pytest.raises(RuntimeError):h.advance_to(181.)
    finally:h.export_close()
    assert h.summary['unresolved_allocations']
    assert h.manager.get_snapshot('abort')['resources']['medic']['available_qty']==0
    assert not any(e['kind']=='RESOURCE_RELEASED' for e in h.events)


def test_runner_refuses_reuse_and_native_fault_injection():
    import tempfile
    from pathlib import Path
    from core301.paths import PROJECT_ROOT
    from core301.research_runtime.m3b_runner import run
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'experiments/results') as root:
        (Path(root)/'exists').mkdir()
        with pytest.raises(FileExistsError):asyncio.run(run('dual_native','exists',root))
        with pytest.raises(ValueError,match='only offline'):asyncio.run(run('dual_native','new',root,faults={'A':{'unknown':True}}))
