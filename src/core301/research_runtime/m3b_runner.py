"""Two isolated patients, one ledger and a barrier clock. No LLM calls."""
import argparse
import asyncio
from dataclasses import dataclass
import json
import math
from pathlib import Path
from uuid import uuid4
from core301.paths import PROJECT_ROOT, PULSE_ROOT
from core301.pulse.observation_projector import REQUESTS,BASIC,ObservationAccess
from core301.pulse.v2.injury_adapter import InjuryAdapter
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.dispatch.complete_contracts import CompletePlan,CompleteAction
from core301.dispatch.shared_resources import SharedResourceManager
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.eta import FakeEtaProvider
from .bridge import SharedAuthority,CompleteExecutionBridge
from .runner import dispatch_input,RecordedFixedProvider,dump
from .evaluation import sha,verify_rules,evaluate
from .pulse_worker import PulseWorkerSession
from .m3b_fake import FakePulseWorker
from .m3b_smoke import casualty

FIELDS=tuple(k for k in REQUESTS if not k.startswith('neurologic.'))
GRANTS=frozenset(FIELDS)-frozenset(BASIC)


def append(path,value):
    with path.open('a') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')


def fixed_plan(run_id,patient_id):
    return CompletePlan(schema_version='301.treatment.complete.1',run_id=run_id,patient_id=patient_id,
        plan_id=patient_id+'-plan',scope_kind='research_fixture',scope_id='external_hemorrhage',severity=.4,
        location_id='scene',execution_policy='m2a_serial_execution',parameter_policy='fixed_profile_no_overrides',
        actions=(CompleteAction(action_instance_id=patient_id+'-control',action_type='control_external_bleeding',
                                compartment='RightLeg',depends_on=()),))


@dataclass
class Patient:
    label:str
    directory:Path
    runtime:CaseRuntime
    plan:CompletePlan
    authority:SharedAuthority
    bridge:CompleteExecutionBridge
    state:str='CREATED'
    request_id:str|None=None
    wait_start:float|None=None
    wait_end:float|None=None
    receipt:dict|None=None
    observations:int=0


class MultiPatientResearchRun:
    """All resource and journal mutations stay in this central process.

    Per-patient advancement is sequential inside a barrier; no event/dispatch is
    processed until both acknowledge the same target. Failure halts the run;
    partial advancement is recorded, never rolled back or called synchronized.
    """
    runtime_class=CaseRuntime

    def treatment_time_allowed(self):
        return abs(self.global_simulation_time_s-180)<=1e-6

    def __init__(self,directory,run_id,mode,*,faults=None,event_budget=2000):
        self.directory=Path(directory);self.run_id=run_id;self.mode=mode
        self.global_simulation_time_s=0.;self.patients={};self.events=[];self.halted=False
        self.event_budget=event_budget;self.faults=faults or {};self.registered=False
        self.manager=SharedResourceManager();stock,locations=research_scene({'medic':1})
        self.manager.create_run(run_id,stock,locations);self.coordinator=SharedDispatchCoordinator(self.manager)
        self.pending_events=[60.,180.,181.,480.]
        self.summary={'run_id':run_id,'mode':mode,'real_llm':False,'real_pulse':False,
                      'overall_status':'M3B_IMPLEMENTED_NATIVE_UNVERIFIED' if mode=='offline_test' else 'M3B_BLOCKED',
                      'waiting_status':'WAITING_NOT_VERIFIED','failure':None}
        for name in ('global_events.jsonl','clock_trace.jsonl','scheduling_decisions.jsonl','resource_events.jsonl'):
            (self.directory/name).touch()

    def emit(self,kind,label=None,**detail):
        if len(self.events)>=self.event_budget:raise RuntimeError('EVENT_BUDGET_EXHAUSTED')
        event={'sequence':len(self.events)+1,'run_id':self.run_id,'global_simulation_time_s':self.global_simulation_time_s,
               'kind':kind,'patient_id':self.patients[label].plan.patient_id if label else None,**detail}
        self.events.append(event);append(self.directory/'global_events.jsonl',event)
        return event

    def now(self):
        # Roundoff is tolerated in Pulse, while M2 uses exact monotonic floats.
        return max([self.global_simulation_time_s]+[p.runtime.session.time for p in self.patients.values()])

    def times(self):return {k:p.runtime.session.get_simulation_time() for k,p in self.patients.items()}

    def barrier(self,target):
        times=self.times()
        valid=all(abs(t-target)<=1e-6 for t in times.values()) and len(times)==2
        append(self.directory/'clock_trace.jsonl',{'run_id':self.run_id,'target_s':target,'patient_times_s':times,'synchronized':valid})
        if not valid:raise RuntimeError('CLOCK_DIVERGENCE')
        self.global_simulation_time_s=target

    def advance_to(self,target):
        if self.halted:raise RuntimeError('RUN_HALTED')
        if not math.isfinite(target) or target<self.global_simulation_time_s or target>480:
            raise ValueError('Invalid global target')
        if any(self.global_simulation_time_s<t<target for t in self.pending_events):raise ValueError('Cannot skip pending event')
        delta=target-self.global_simulation_time_s
        self.barrier(self.global_simulation_time_s)
        try:
            for p in self.patients.values():
                if p.runtime._prepared:p.runtime.advance(delta)
                else:p.runtime.session.advance_time(delta)
            self.barrier(target)
            self.pending_events=[t for t in self.pending_events if t>target]
        except Exception:
            self.halted=True
            append(self.directory/'clock_trace.jsonl',{'target_s':target,'synchronized':False,'advance_failed':True,
                'last_acknowledged_times_s':{k:p.runtime.session.time for k,p in self.patients.items()}})
            raise

    def initialize(self):
        verify_rules()
        for label in ('A','B'):
            patient_id=self.run_id+'-'+label;d=self.directory/'patients'/('patient_'+label);d.mkdir(parents=True)
            session=(PulseWorkerSession(self.run_id,patient_id,d,FIELDS) if self.mode=='dual_native' else
                     FakePulseWorker(self.run_id,patient_id,d,FIELDS,self.faults.get(label)))
            plan=fixed_plan(self.run_id,patient_id)
            auth=SharedAuthority(plan,self.coordinator,self.now,d)
            rt=self.runtime_class(patient_id,d/'runtime',run_id=self.run_id,mode='research',resources=auth,
                access=ObservationAccess(GRANTS,GRANTS,GRANTS,GRANTS),session=session)
            p=Patient(label,d,rt,plan,auth,CompleteExecutionBridge(rt,auth));self.patients[label]=p
            dump(d/'complete_plan.json',plan.model_dump(mode='json'))
            (d/'execution_events.jsonl').touch();(d/'observations.jsonl').touch()
            rt.casualty=casualty(patient_id) # exact existing admission, no new patient/profile
            rt._write('injury_input.json',rt.casualty.model_dump())
            session.initialize(d/'runtime/pulse.log')
            (d/'initial_state.json').write_text(session.serialize_state())
            if self.mode=='dual_native':
                (d/'patient_input.json').write_bytes((PULSE_ROOT/'patients/StandardMale.json').read_bytes())
                (d/'patient_initial_state.json').write_bytes((PULSE_ROOT/'states/StandardMale@0s.json').read_bytes())
        self.barrier(0.)
        self.emit('SCENARIO_INITIALIZED',worker_pids={k:p.runtime.session.worker_pid for k,p in self.patients.items()})
        self.advance_to(60.)
        for label,p in self.patients.items():
            for injury in p.runtime.casualty.dynamic_injuries:
                p.runtime.session._submit(InjuryAdapter().convert_dynamic(injury),'injury')
            self.emit('INJURY_APPLIED',label)
        self.advance_to(180.)
        for label,p in self.patients.items():
            p.runtime.registry.register(p.runtime.casualty);p.runtime._prepared=True
            p.runtime._write('initialization_result.json',{'accepted':True,'simulation_time_s':p.runtime.session.time,
                'injury_records':p.runtime.session.action_results,'phased_by_global_clock':True})
            (p.directory/'pretreatment_state.json').write_text(p.runtime.session.serialize_state())
            p.state='PLAN_READY';self.emit('PLAN_READY',label,plan_id=p.plan.plan_id)
        self.summary['real_pulse']=self.mode=='dual_native'
        sources=[dispatch_input(p.plan,p.runtime.observe()) for p in self.patients.values()]
        self.coordinator.register_run(self.run_id,sources,at_s=self.now(),
                                      patient_locations={p.plan.patient_id:'scene' for p in self.patients.values()})
        self.registered=True;self.capture()

    def capture(self):
        self.barrier(self.global_simulation_time_s)
        for label,p in self.patients.items():
            obs=p.runtime.observe()
            measurements={}
            for name in FIELDS:
                group,field=name.split('.');m=getattr(getattr(obs,group,None),field,None)
                if m is not None:measurements[name]={**m.model_dump(),'unit':REQUESTS[name][2] or '1'}
            row={'run_id':self.run_id,'patient_id':p.plan.patient_id,'plan_id':p.plan.plan_id,
                 'worker_pid':p.runtime.session.worker_pid,'global_simulation_time_s':self.global_simulation_time_s,
                 'simulation_time_s':obs.simulation_time_s,'patient_observation':obs.model_dump(),
                 'measurements':measurements,'diagnostics':p.runtime.session.diagnostics(),
                 'native_events':p.runtime.session.active_events(),'mode':self.mode,'patient_state':p.state}
            append(p.directory/'observations.jsonl',row);p.observations+=1
            self.emit('OBSERVATION_CAPTURED',label,observation_index=p.observations)

    async def schedule(self,label,request=None):
        if self.halted:raise RuntimeError('RUN_HALTED')
        self.barrier(self.global_simulation_time_s)
        p=self.patients[label];req=request or p.authority.request('schedule')
        self.emit('RESOURCE_REQUESTED',label,request=req.model_dump(mode='json'))
        result=await self.coordinator.schedule_complete(req,p.plan,RecordedFixedProvider(p.plan.patient_id,p.directory),FakeEtaProvider({}))
        append(self.directory/'scheduling_decisions.jsonl',{'patient_label':label,'global_simulation_time_s':self.global_simulation_time_s,
            'request':req.model_dump(mode='json'),'result':result.model_dump(mode='json')})
        dump(p.directory/('dispatch_'+str(p.authority.sequence)+'.json'),result.model_dump(mode='json'))
        if result.allocated:
            p.authority.task_id=result.task.task_id;p.state='RESOURCE_RESERVED'
            self.emit('RESOURCE_RESERVED',label,task_id=result.task.task_id,allocation_ids=list(result.resource_result.allocation_ids))
        else:
            self.emit('RESOURCE_BLOCKED',label,result=result.model_dump(mode='json'))
            if p.wait_start is None:
                p.wait_start=self.global_simulation_time_s;p.state='WAITING_RESOURCE'
                self.emit('PATIENT_WAITING',label,plan_id=p.plan.plan_id,
                    observed_resource_version=result.resource_result.state_version,
                    conflicts=[c.model_dump(mode='json') for c in result.resource_result.conflicts],
                    waiting_reason='shared resource conflict',next_review_trigger='RESOURCE_RELEASED or SCENARIO_END')
        return result

    def execute(self,label):
        if self.halted:raise RuntimeError('RUN_HALTED')
        self.barrier(self.global_simulation_time_s);p=self.patients[label]
        if not self.treatment_time_allowed():
            p.state='TIME_PROTOCOL_BLOCKED';self.emit('TIME_PROTOCOL_BLOCKED',label,code='UNVALIDATED_TIMING',allowed_time_s=180)
            return False
        if p.authority.task_id is None:raise ValueError('No confirmed resource task')
        if p.request_id is not None:raise ValueError('Execution already submitted; query original receipt')
        context=p.runtime.build_context();p.request_id=p.plan.patient_id+'-execute'
        allocations=[a for a,v in self.manager.get_snapshot(self.run_id)['allocations'].items() if v['plan_id']==p.plan.plan_id]
        identity={'run_id':self.run_id,'patient_id':p.plan.patient_id,'plan_id':p.plan.plan_id,
                  'action_instance_id':p.plan.actions[0].action_instance_id,'task_id':p.authority.task_id,'allocation_ids':allocations}
        p.runtime.session.bind_execution(identity)
        self.emit('TREATMENT_STARTED',label,**{k:v for k,v in identity.items() if k not in ('run_id','patient_id')})
        try:
            p.receipt=p.bridge.execute(p.plan,request_id=p.request_id,context_ref=context.context_ref)
            dump(p.directory/'execution_receipt.json',p.receipt)
            p.state='ACCEPTED_PENDING_CONFIRMATION';self.emit('TREATMENT_ACCEPTED',label,request_id=p.request_id)
            return True
        except Exception:
            p.receipt=p.runtime.query(p.request_id)
            if p.receipt:dump(p.directory/'execution_receipt.json',p.receipt)
            p.state='EXECUTION_UNRESOLVED';self.halted=True
            self.emit('EXECUTION_UNKNOWN',label,receipt=p.receipt)
            raise

    def release_confirmed(self,label):
        p=self.patients[label];record=p.runtime.query(p.request_id)
        p.authority.finish(record) # rejects accepted-only, unknown, wrong identity
        p.receipt=record;dump(p.directory/'execution_receipt_final.json',record)
        for operation in ('confirm_onsite','end_episode'):
            result=self.coordinator.lifecycle(p.authority.request(operation),p.authority.task_id,operation)
            p.authority.require(result.resource_result)
        p.state='TREATMENT_COMPLETED'
        return self.emit('RESOURCE_RELEASED',label,plan_id=p.plan.plan_id,
                         state_version=self.manager.get_snapshot(self.run_id)['state_version'])

    def priority_order(self):
        return ("A", "B") # historical M3-B default; M3-C1 overrides admission

    async def episode(self):
        self.initialize()
        selected,waiting=self.priority_order()
        a=await self.schedule(selected);b=await self.schedule(waiting)
        if not a.allocated or b.allocated:raise RuntimeError('Expected real one-token contention not observed')
        self.execute(selected)
        self.advance_to(181.);self.capture()
        release=self.release_confirmed(selected)
        p=self.patients[waiting]
        self.emit('RESOURCE_CHANGE_OBSERVED',waiting,trigger_sequence=release['sequence'],
                  state_version=self.manager.get_snapshot(self.run_id)['state_version'])
        second=await self.schedule(waiting)
        if not second.allocated:raise RuntimeError('Fresh resource recovery check failed')
        p.wait_end=self.global_simulation_time_s
        self.emit('WAIT_ENDED',waiting,wait_start_s=p.wait_start,wait_end_s=p.wait_end,
                  duration_s=p.wait_end-p.wait_start,trigger_sequence=release['sequence'])
        if not self.execute(waiting):
            cancelled=self.coordinator.lifecycle(p.authority.request('cancel'),p.authority.task_id,'cancel',
                                                detail='UNVALIDATED_TIMING: unused reservation cancelled; no treatment submitted')
            p.authority.require(cancelled.resource_result)
            self.emit('UNUSED_RESERVATION_CANCELLED',waiting,result=cancelled.model_dump(mode='json'))
        for t in range(182,481):self.advance_to(float(t));self.capture()
        for p in self.patients.values():
            (p.directory/'final_state.json').write_text(p.runtime.session.serialize_state())
            if self.mode=='dual_native' and p.receipt and p.receipt['status']=='COMPLETED':
                rows=[json.loads(line) for line in (p.directory/'observations.jsonl').read_text().splitlines()]
                dump(p.directory/'native_events.json',{'complete':False,'sampling_s':1,'records':[
                    {'time_s':r['simulation_time_s'],'active_events':r['native_events']} for r in rows]})
                result=evaluate(p.directory,p.plan,self.global_simulation_time_s)
            else:
                result={'evaluator_called':False,'computation_state':'NOT_EVALUABLE' if self.mode=='dual_native' else 'NOT_RUN',
                        'grade':None,'reason':'No treatment: fixed 180s timing blocked; dynamic untreated branch is outside locked treatment scoring' if self.mode=='dual_native' else 'OFFLINE_FAKE'}
            dump(p.directory/'evaluation_result.json',result)
        self.summary.update(overall_status='M3B_DUAL_PATIENT_PARTIAL' if self.mode=='dual_native' else 'M3B_IMPLEMENTED_NATIVE_UNVERIFIED',
            waiting_status='WAITING_TIME_ADVANCEMENT_VERIFIED' if self.mode=='dual_native' else 'WAITING_NOT_VERIFIED',
            waiting_duration_s=self.patients[waiting].wait_end-self.patients[waiting].wait_start,
            endpoint_reached=True,time_protocol_blocked_patient=waiting,selected_patient=selected)
        self.emit('SCENARIO_COMPLETED')

    def export_close(self):
        for label,p in self.patients.items():
            session=p.runtime.session
            dump(p.directory/'native_action_results.json',session.action_results)
            state={'patient_id':p.plan.patient_id,'plan_id':p.plan.plan_id,'state':p.state,'worker_pid':session.worker_pid,
                   'last_acknowledged_time_s':session.time,'observations':p.observations,
                   'treatment_count':sum(a['phase']=='treatment' for a in session.action_results),
                   'wait_start_s':p.wait_start,'wait_end_s':p.wait_end,'mode':self.mode}
            dump(p.directory/'patient_summary.json',state)
            try:p.runtime.close()
            except Exception as exc:self.summary.setdefault('close_errors',[]).append(type(exc).__name__)
            finally:session.close()
        snapshot=self.manager.get_snapshot(self.run_id)
        dump(self.directory/'resource_final.json',snapshot)
        for event in self.manager.get_events(self.run_id):append(self.directory/'resource_events.jsonl',event)
        if self.registered:dump(self.directory/'dispatch_history.json',self.coordinator.get_history(self.run_id))
        self.summary.update(global_simulation_time_s=self.global_simulation_time_s,
            unresolved_allocations=[k for k,v in snapshot['allocations'].items() if v['status'] in ('RESERVED','IN_USE','QUARANTINED')])
        dump(self.directory/'run_summary.json',self.summary)
        dump(self.directory/'sha256_manifest.json',{str(p.relative_to(self.directory)):sha(p) for p in sorted(self.directory.rglob('*'))
             if p.is_file() and p.name!='sha256_manifest.json'})


async def run(mode='offline_test',run_id=None,output_root=None,*,faults=None,event_budget=2000):
    if mode not in ('offline_test','dual_native'):raise ValueError('Unknown mode')
    if mode=='dual_native' and faults:raise ValueError('Fault injection only offline')
    run_id=run_id or 'm3b-'+uuid4().hex
    if Path(run_id).name!=run_id or run_id in ('.','..'):raise ValueError('Invalid run id')
    root=Path(output_root or PROJECT_ROOT/'experiments/results/m3b_dual_patient').resolve()
    if not root.is_relative_to(PROJECT_ROOT):raise ValueError('Output must remain in project')
    d=root/run_id;d.mkdir(parents=True,exist_ok=False)
    scenario={'scenario_id':'dual_external_rightleg04_contention_v1','patients':['A','B'],
              'baseline':'StandardMale','injury':'external_hemorrhage','severity':.4,'compartment':'RightLeg',
              'resource_fixture':{'medic':1},'priority':['A','B'],'timeline_s':{'injury':60,'decision':180,'confirmation_sample':181,'endpoint':480},
              'confirmation_sample_not_clinical_duration':True}
    dump(d/'scenario.json',scenario)
    dump(d/'run_manifest.json',{'run_id':run_id,'mode':mode,'scenario':scenario['scenario_id'],'real_llm':False,
        'treatment_provider':'fixed host CompletePlan','dispatch_provider':'FixedDispatchProvider onsite',
        'isolation':'spawn processes' if mode=='dual_native' else 'FAKE sessions',
        'pulse_version':'4.3.2','complete_plan_version':'301.treatment.complete.1','resources_version':'301.resource.m2a.1',
        'rule_version':'RESEARCH_RULESET_V1_LOCKED','fifteen_metric_activation':False,
        'source_sha256':{name:sha(PROJECT_ROOT/name) for name in [
            'src/core301/research_runtime/m3b_runner.py','src/core301/research_runtime/pulse_worker.py',
            'src/core301/runtime/v2/case_runtime.py','src/core301/dispatch/shared_resources/manager.py']}})
    host=MultiPatientResearchRun(d,run_id,mode,faults=faults,event_budget=event_budget)
    try:await host.episode()
    except Exception as exc:
        host.halted=True;host.summary['failure']={'type':type(exc).__name__,'message':str(exc)}
        host.summary['overall_status']='M3B_BLOCKED'
    finally:host.export_close()
    return d,host.summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['offline_test','dual_native'],default='offline_test');p.add_argument('--run-id')
    args=p.parse_args();d,r=asyncio.run(run(args.mode,args.run_id))
    print(json.dumps({'directory':str(d),**r},ensure_ascii=False,indent=2))
    return 1 if r['overall_status']=='M3B_BLOCKED' else 0

if __name__=='__main__':raise SystemExit(main())
