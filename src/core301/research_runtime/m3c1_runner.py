"""One priority decision, the shared M3-B execution path, and immutable run evidence."""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4
from core301.paths import PROJECT_ROOT
from core301.agent.priority_decision import build_input, parse_decision, validate_decision, FixedPriorityProvider
from core301.agent.priority_provider import LLMPriorityDecisionProvider, PROMPT_SHA
from .m3b_runner import MultiPatientResearchRun, dump
from .evaluation import sha

class PriorityResearchRun(MultiPatientResearchRun):
    def __init__(self,*args,priority_mode='fixed_A_first',provider=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.priority_mode=priority_mode
        self.provider=provider
        self.summary.update(priority_mode=priority_mode,overall_status='M3C1_IMPLEMENTED_NATIVE_UNVERIFIED')

    def priority_order(self):
        payload=build_input(self)
        dump(self.directory/'priority_agent_input.json',payload)
        try:
            provider=self.provider or (LLMPriorityDecisionProvider() if self.priority_mode=='llm_priority' else FixedPriorityProvider(self.priority_mode))
            raw=provider.create_decision(payload,self.directory)
            dump(self.directory/'priority_raw_output.json',{'content':raw,'provider_mode':self.priority_mode})
            self.summary['real_llm']=self.priority_mode=='llm_priority' and (self.directory/'llm_response.json').exists()
            decision=parse_decision(raw)
            dump(self.directory/'priority_decision.json',decision.model_dump(mode='json'))
            validate_decision(decision,payload,current_time=self.global_simulation_time_s,
                current_version=self.manager.get_snapshot(self.run_id)['state_version'])
            ids={p.plan.patient_id:label for label,p in self.patients.items()}
            order=tuple(ids[pid] for pid in decision.ordered_patient_ids)
            dump(self.directory/'decision_validation.json',{'status':'PASS','ordered_patient_ids':decision.ordered_patient_ids,
                'current_time_s':self.global_simulation_time_s,'resource_state_version':payload['resource_state_version']})
            self.emit('PRIORITY_ADMITTED',ordered_patient_ids=decision.ordered_patient_ids)
            return order
        except Exception as exc:
            dump(self.directory/'decision_validation.json',{'status':'BLOCKED','error_type':type(exc).__name__})
            raise

async def run(mode='offline_test',priority_mode='fixed_A_first',run_id=None,output_root=None):
    if mode not in ('offline_test','dual_native'):raise ValueError('Unknown runtime mode')
    if priority_mode not in ('fixed_A_first','fixed_B_first','llm_priority'):raise ValueError('Unknown priority mode')
    if priority_mode=='llm_priority' and mode!='dual_native':raise ValueError('Real LLM requires real patient observations')
    run_id=run_id or 'm3c1-'+uuid4().hex
    if Path(run_id).name!=run_id or run_id in ('.','..'):raise ValueError('Invalid run id')
    root=Path(output_root or PROJECT_ROOT/'experiments/results/m3c1_priority_decision').resolve()
    if not root.is_relative_to(PROJECT_ROOT):raise ValueError('Output must remain inside V2')
    d=root/run_id;d.mkdir(parents=True,exist_ok=False)
    manifest={'run_id':run_id,'mode':mode,'priority_mode':priority_mode,'real_llm':False,
        'llm_call_limit':1 if priority_mode=='llm_priority' else 0,'prompt_sha256':PROMPT_SHA,
        'treatment_provider':'fixed host CompletePlan','dispatch_provider':'FixedDispatchProvider onsite',
        'source_sha256':{str(p.relative_to(PROJECT_ROOT)):sha(p) for p in [
            *PROJECT_ROOT.glob('src/core301/agent/priority*.py'),
            PROJECT_ROOT/'src/core301/agent/prompts/priority_decision_m3c1.md',
            *PROJECT_ROOT.glob('src/core301/research_runtime/m3c1*.py'),
            PROJECT_ROOT/'src/core301/research_runtime/m3b_runner.py']}}
    dump(d/'run_manifest.json',manifest)
    dump(d/'scenario.json',{'patients':['A','B'],'baseline':'StandardMale','injury':'external_hemorrhage',
        'severity':.4,'compartment':'RightLeg','medic':1,'priority_mode':priority_mode,
        'timeline_s':{'injury':60,'decision':180,'confirmation_sample':181,'endpoint':480}})
    host=PriorityResearchRun(d,run_id,mode,priority_mode=priority_mode)
    try:
        await host.episode()
        host.summary['overall_status']='M3C1_PARTIAL' if mode=='dual_native' else 'M3C1_IMPLEMENTED_NATIVE_UNVERIFIED'
    except Exception as exc:
        host.halted=True
        # Do not persist arbitrary provider exception text (may contain credentials).
        host.summary.update(failure={'type':type(exc).__name__},overall_status='M3C1_PARTIAL')
        if any(p.request_id for p in host.patients.values()):host.summary['overall_status']='M3C1_BLOCKED'
    finally:
        manifest['real_llm']=host.summary['real_llm'];dump(d/'run_manifest.json',manifest)
        host.export_close()
    return d,host.summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['offline_test','dual_native'],default='offline_test')
    p.add_argument('--priority-mode',choices=['fixed_A_first','fixed_B_first','llm_priority'],default='fixed_A_first')
    p.add_argument('--run-id');a=p.parse_args()
    d,s=asyncio.run(run(a.mode,a.priority_mode,a.run_id))
    print(json.dumps({'directory':str(d),**s},indent=2))
    return int(bool(s['failure']))

if __name__=='__main__':raise SystemExit(main())
