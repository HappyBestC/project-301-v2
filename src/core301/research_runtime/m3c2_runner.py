"""Bounded event-driven feedback; frozen real-agent experiment and separate timing exploration."""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4
from core301.paths import PROJECT_ROOT,PULSE_ROOT
from core301.agent.resource_feedback import build_feedback,parse_decision,validate_decision,FixedFeedbackProvider
from core301.agent.feedback_provider import LLMTreatmentFeedbackProvider,PROMPT_SHA
from core301.runtime.v2.case_runtime import CaseRuntime
from .m3c1_runner import PriorityResearchRun
from .m3b_runner import append,dump
from .m3c2_timing import DynamicTimingCaseRuntime,protocol,time_allowed
from .evaluation import verify_rules,sha,evaluate
from .bridge import executor_plan

class ResourceFeedbackController:
    def __init__(self,host,provider):
        self.host=host;self.provider=provider;self.calls=0;self.handled=set();self.decisions=[]
    async def decide(self,label,result,trigger=None):
        h=self.host
        key=(label,trigger)
        if key in self.handled or self.calls>=2:raise RuntimeError('FEEDBACK_PROGRESS_OR_CALL_LIMIT')
        self.handled.add(key);self.calls+=1
        decision_id=f'{h.run_id}-feedback-{self.calls}'
        f,payload=build_feedback(h,label,result,decision_id=decision_id,trigger=trigger)
        append(h.directory/'resource_feedback.jsonl',f.model_dump(mode='json'))
        append(h.directory/'feedback_agent_input.jsonl',payload)
        raw=self.provider.create_decision(payload,h.directory)
        append(h.directory/'feedback_raw_outputs.jsonl',{'decision_id':decision_id,'content':raw})
        d=parse_decision(raw)
        validate_decision(d,f,current_version=h.manager.get_snapshot(h.run_id)['state_version'],current_time=h.global_simulation_time_s)
        append(h.directory/'feedback_decisions.jsonl',d.model_dump(mode='json'))
        self.decisions.append(d.decision_type)
        h.emit('FEEDBACK_DECISION_ADMITTED',label,decision_id=decision_id,decision_type=d.decision_type,trigger_sequence=trigger)
        p=h.patients[label];kind=d.decision_type
        if kind=='KEEP_PLAN_AND_WAIT':
            p.state='WAITING_FEEDBACK_EVENT'
            h.emit('FEEDBACK_WAIT_REGISTERED',label,decision_id=decision_id,condition=f.next_check_condition)
        elif kind=='DEFER_INSUFFICIENT_EVIDENCE':
            p.state='DEFERRED';h.emit('FEEDBACK_DEFERRED',label,decision_id=decision_id,reason=d.refusal_reason)
        elif kind=='STOP_UNEXECUTABLE':
            h.cancel_unused(label,'Agent STOP_UNEXECUTABLE')
            p.state='STOPPED_UNEXECUTABLE' if not f.unresolved_execution else 'UNKNOWN_RETAINED'
            h.emit('FEEDBACK_STOPPED',label,decision_id=decision_id,unresolved_execution=f.unresolved_execution)
        elif kind=='RECHECK_RESOURCES':
            h.emit('FEEDBACK_RECHECK',label,decision_id=decision_id,state_version=h.manager.get_snapshot(h.run_id)['state_version'])
            second=await h.schedule(label)
            if second.allocated:
                p.wait_end=h.global_simulation_time_s
                h.emit('WAIT_ENDED',label,decision_id=decision_id,wait_start_s=p.wait_start,wait_end_s=p.wait_end,
                       duration_s=p.wait_end-p.wait_start,trigger_sequence=trigger)
                if not h.execute(label):h.cancel_unused(label,'UNVALIDATED_TIMING')
            else:
                p.state='RECHECK_BLOCKED';h.emit('RECHECK_TERMINATED',label,decision_id=decision_id,result=second.model_dump(mode='json'))
        return d

class FeedbackResearchRun(PriorityResearchRun):
    def __init__(self,*args,feedback_provider=None,exploratory=False,**kwargs):
        self.exploratory=exploratory;self.timing=protocol(exploratory)
        self.runtime_class=DynamicTimingCaseRuntime if exploratory else CaseRuntime
        super().__init__(*args,**kwargs)
        self.feedback_controller=ResourceFeedbackController(self,feedback_provider or FixedFeedbackProvider())
    def treatment_time_allowed(self):return time_allowed(self.global_simulation_time_s,self.exploratory)
    def cancel_unused(self,label,reason):
        p=self.patients[label];snapshot=self.manager.get_snapshot(self.run_id)
        owned=[a for a in snapshot['allocations'].values() if a['plan_id']==p.plan.plan_id]
        if any(a['status'] in ('IN_USE','QUARANTINED') for a in owned):
            self.emit('UNKNOWN_OR_IN_USE_RETAINED',label);return
        if p.authority.task_id and any(a['status']=='RESERVED' for a in owned):
            result=self.coordinator.lifecycle(p.authority.request('cancel'),p.authority.task_id,'cancel',detail=reason)
            p.authority.require(result.resource_result);self.emit('UNUSED_RESERVATION_CANCELLED',label,result=result.model_dump(mode='json'))
    async def episode(self):
        self.initialize();selected,waiting=self.priority_order()
        first=await self.schedule(selected);blocked=await self.schedule(waiting)
        if not first.allocated or blocked.allocated:raise RuntimeError('Expected real M2 contention absent')
        self.execute(selected)
        await self.feedback_controller.decide(waiting,blocked)
        self.advance_to(181.);self.capture();release=self.release_confirmed(selected)
        p=self.patients[waiting]
        if p.state=='WAITING_FEEDBACK_EVENT':
            self.emit('FEEDBACK_WAKE',waiting,trigger_sequence=release['sequence'],state_version=self.manager.get_snapshot(self.run_id)['state_version'])
            await self.feedback_controller.decide(waiting,blocked,release['sequence'])
        for t in range(182,481):
            self.advance_to(float(t));self.capture()
            if t==182 and p.request_id:self.release_confirmed(waiting)
        for patient in self.patients.values():
            (patient.directory/'final_state.json').write_text(patient.runtime.session.serialize_state())
            if self.mode=='dual_native' and not self.exploratory and patient.receipt and patient.receipt['status']=='COMPLETED':
                rows=[json.loads(x) for x in (patient.directory/'observations.jsonl').read_text().splitlines()]
                dump(patient.directory/'native_events.json',{'complete':False,'sampling_s':1,'records':[
                    {'time_s':r['simulation_time_s'],'active_events':r['native_events']} for r in rows]})
                evaluation=evaluate(patient.directory,patient.plan,480.)
            else:
                evaluation={'evaluator_called':False,'computation_state':'NOT_EVALUABLE','grade':None,
                    'reason':'Exploratory timing lacks matched formal evaluation evidence' if self.exploratory else 'Untreated or offline evidence'}
            dump(patient.directory/'evaluation_result.json',evaluation)
        self.summary.update(overall_status='M3C2_PENDING_INDEPENDENT_VERIFICATION',selected_patient=selected,waiting_patient=waiting,
            feedback_decisions=self.feedback_controller.decisions,feedback_calls=self.feedback_controller.calls,
            endpoint_reached=True,exploratory=self.exploratory,waiting_status='REAL_ADVANCEMENT' if self.mode=='dual_native' else 'OFFLINE_ONLY')
        self.emit('SCENARIO_COMPLETED')

async def timing_preflight(directory):
    """Actual isolated fake/M2 probes; no new native treatment before these pass."""
    verify_rules()
    for rel,key in [('patients/StandardMale.json','patient_sha256'),('states/StandardMale@0s.json','state_sha256')]:
        if sha(PULSE_ROOT/rel)!=protocol(True)[key]:raise ValueError('Patient provenance mismatch')
    checks={}
    with tempfile.TemporaryDirectory(dir=directory) as root:
        for dynamic in (False,True):
            d=Path(root)/str(dynamic);d.mkdir()
            h=FeedbackResearchRun(d,'admission-'+str(dynamic),'offline_test',exploratory=dynamic)
            try:
                h.initialize();a=await h.schedule('A');b=await h.schedule('B')
                assert a.allocated and not b.allocated
                h.execute('A');h.advance_to(181.);h.release_confirmed('A');assert (await h.schedule('B')).allocated
                p=h.patients['B'];source,=p.runtime.registry.sources()
                command=executor_plan(p.plan)
                try:p.runtime.validate_treatment_timing(command,source,181.)
                except Exception:
                    if dynamic:raise
                    checks['old_runtime_181_rejected']=True
                else:
                    if not dynamic:raise AssertionError('Old timing opened')
                accepted=h.execute('B');assert accepted==dynamic
                checks['dynamic_181_full_executor' if dynamic else 'old_runner_181_rejected']=True
                try:p.runtime.validate_treatment_timing(command,source,182.)
                except Exception:checks['dynamic_182_rejected' if dynamic else 'old_182_rejected']=True
                else:raise AssertionError('Unlisted time admitted')
                if dynamic:
                    h.advance_to(182.);h.release_confirmed('B')
                else:h.cancel_unused('B','preflight frozen timing')
                assert h.manager.get_snapshot(h.run_id)['resources']['medic']['available_qty']==1
            finally:h.export_close()
    report={'status':'PASS','evidence_kind':'FAKE_CONTRACT_AND_REAL_M2_ONLY','checks':checks,'protocol':protocol(True)}
    dump(Path(directory)/'timing_admission.json',report);return report

async def run(mode='offline_test',run_id=None,output_root=None,*,fixed_decisions=None,priority_mode='fixed_A_first'):
    if mode not in ('offline_test','feedback_native','timing_exploratory'):raise ValueError('Unknown mode')
    if mode=='feedback_native' and fixed_decisions is not None:raise ValueError('Real mode cannot substitute fixed feedback')
    if priority_mode not in ('fixed_A_first','fixed_B_first'):raise ValueError('M3-C2 uses fixed priority only')
    run_id=run_id or 'm3c2-'+uuid4().hex
    if Path(run_id).name!=run_id or run_id in ('.','..'):raise ValueError('Invalid run id')
    root=Path(output_root or PROJECT_ROOT/'experiments/results/m3c2_feedback_decision').resolve()
    if not root.is_relative_to(PROJECT_ROOT):raise ValueError('Results must stay inside V2')
    d=root/run_id;d.mkdir(parents=True,exist_ok=False)
    exploratory=mode=='timing_exploratory'
    manifest={'run_id':run_id,'mode':mode,'real_pulse':mode!='offline_test','real_llm':False,'priority_mode':priority_mode,
        'feedback_provider':'LLMTreatmentFeedbackProvider' if mode=='feedback_native' else 'FixedFeedbackProvider',
        'max_llm_calls':2 if mode=='feedback_native' else 0,'prompt_sha256':PROMPT_SHA,
        'source_sha256':{str(p.relative_to(PROJECT_ROOT)):sha(p) for p in [
            *PROJECT_ROOT.glob('src/core301/research_runtime/m3c2*.py'),
            PROJECT_ROOT/'src/core301/research_runtime/m3b_runner.py',PROJECT_ROOT/'src/core301/runtime/v2/case_runtime.py',
            PROJECT_ROOT/'src/core301/agent/resource_feedback.py',PROJECT_ROOT/'src/core301/agent/feedback_provider.py',
            PROJECT_ROOT/'src/core301/agent/prompts/resource_feedback_decision_m3c2.md']}}
    dump(d/'run_manifest.json',manifest);dump(d/'timing_protocol.json',protocol(exploratory))
    for name in ('resource_feedback.jsonl','feedback_agent_input.jsonl','llm_requests.jsonl','llm_responses.jsonl','feedback_decisions.jsonl','feedback_raw_outputs.jsonl'):(d/name).touch()
    host=FeedbackResearchRun(d,run_id,'offline_test' if mode=='offline_test' else 'dual_native',exploratory=exploratory,priority_mode=priority_mode)
    try:
        if exploratory:await timing_preflight(d)
        if mode=='feedback_native':host.feedback_controller.provider=LLMTreatmentFeedbackProvider()
        else:host.feedback_controller.provider=FixedFeedbackProvider(fixed_decisions or ('KEEP_PLAN_AND_WAIT','RECHECK_RESOURCES'))
        await host.episode()
    except Exception as exc:
        host.halted=True;host.summary.update(failure={'type':type(exc).__name__},overall_status='M3C2_BLOCKED')
    finally:
        manifest['real_llm']=(d/'llm_responses.jsonl').stat().st_size>0
        host.summary.update(real_llm=manifest['real_llm'],experiment_mode=mode,
            feedback_calls=host.feedback_controller.calls,feedback_decisions=host.feedback_controller.decisions)
        dump(d/'run_manifest.json',manifest);host.export_close()
    return d,host.summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['offline_test','feedback_native','timing_exploratory'],default='offline_test')
    p.add_argument('--run-id');p.add_argument('--priority-mode',choices=['fixed_A_first','fixed_B_first'],default='fixed_A_first');a=p.parse_args()
    d,s=asyncio.run(run(a.mode,a.run_id,priority_mode=a.priority_mode));print(json.dumps({'directory':str(d),**s},indent=2))
    return int(bool(s['failure']))

if __name__=='__main__':raise SystemExit(main())
