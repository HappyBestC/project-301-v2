"""Bounded real Agent -> validator -> feedback loop. Never executes the schedule."""
import argparse
import asyncio
import copy
import json
from pathlib import Path
from .api import build_input, load_config, load_cases, make_tasks
from .demo import write
from .coverage import accounting, SUMMARY_KEYS
from .feedback import build_feedback

async def run_agent(provider, context, output, *, max_attempts=3, timeout_s=180):
    if not 1<=max_attempts<=5:raise ValueError('max_attempts must be between 1 and 5')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frozen=copy.deepcopy(context)
    write(output/'dispatch_input.json',context)
    previous=feedback=None;latest=None;history=[];best=None;known_conflicts={};previous_selected=set()
    summary={**accounting(context),'known_constraints_passed':False,'fully_verified':False,'status':'running','model':provider._config.model,'loaded_patients':len(context['patients']),
             'horizon_min':context['horizon_min'],'observation_time_min':context.get('observation_time_min',60),'attempts':history,'treatment_executed':False,
             'resources_committed':False,'accepted_patients':0,'source':'live_agent_not_fixed_example'}
    write(output/'summary.json',summary)
    for n in range(1,max_attempts+1):
        directory=output/f'attempt_{n:02}'
        directory.mkdir(parents=True,exist_ok=False)
        print(f'Agent attempt {n}/{max_attempts}: requesting schedule',flush=True)
        try:
            latest=await provider.decide_resource_schedule(copy.deepcopy(context),feedback=feedback,
                        previous_response=previous,timeout_s=timeout_s,audit_dir=directory)
        except Exception as exc:
            # Do not persist arbitrary exception strings, response headers or credentials.
            failure={'error_type':type(exc).__name__,'status_code':getattr(exc,'status_code',None)}
            write(output/'request_error.json',failure)
            summary.update(status='request_or_adapter_failed',error=failure)
            break
        validation=latest['validation']
        write(directory/'candidate_schedule.json',latest['schedule'])
        write(directory/'validation.json',validation)
        history.append({'attempt':n,'conflicts':len(validation['conflicts']),
                        'unchecked':len(validation.get('unchecked',[])),
                        'selected_patients':len(latest['schedule'].get('selections',{})) if isinstance(latest['schedule'],dict) else 0})
        print(f"Agent attempt {n}: {history[-1]['conflicts']} conflicts, {history[-1]['unchecked']} unchecked",flush=True)
        candidate=latest['schedule'] if isinstance(latest['schedule'],dict) else {}
        selected=set(candidate.get('selections',{}))
        feedback=build_feedback(context,candidate,validation,n,known_conflicts,previous_selected)
        write(directory/'feedback.json',feedback)
        if not validation['conflicts']:
            if best is None or validation['scheduled_patients']>best[1]['validation']['scheduled_patients']:
                best=(n,copy.deepcopy(latest))
            remaining=validation['unscheduled_reasons']
            if not remaining or all(x['reason_code']=='missing_parameters' for x in remaining):
                break
        previous_selected=selected
        previous=latest['raw_response']
        summary['status']='conflicts_retrying' if validation['conflicts'] else 'coverage_retrying'
        write(output/'summary.json',summary)
    if latest is not None:
        write(output/'last_candidate.json',latest['schedule'])
        write(output/'last_validation.json',latest['validation'])
    if best is not None:
        accepted_attempt,accepted=best
        validation=accepted['validation']
        write(output/'schedule.json',accepted['schedule'])
        write(output/'validation.json',validation)
        write(output/'observation_summary.json',validation['observation_summary'])
        write(output/'planning_summary.json',validation['planning_summary'])
        write(output/'occupancy.json',validation['projected_occupancy'])
        write(output/'inventory_changes.json',validation['projected_inventory_changes'])
        write(output/'task_requests.json',make_tasks(context,accepted['schedule']['selections']))
        summary.update({k:validation[k] for k in SUMMARY_KEYS})
        summary.update(status='all_scheduled' if validation['all_patients_scheduled'] else 'partial_schedule',
                       accepted_attempt=accepted_attempt,accepted_patients=validation['scheduled_patients'],known_constraints_passed=True,
                       fully_verified=validation['fully_verified'],
                       unchecked_codes=sorted({x['code'] for x in validation['unchecked']}),
                       not_selected_patient_ids=validation['unscheduled_patient_ids'],
                       explanation_assessment='model_explanation_not_infeasibility_proof')
    elif latest is not None:
        validation=latest['validation']
        write(output/'validation.json',validation)
        summary.update({k:validation[k] for k in SUMMARY_KEYS if k in validation})
        if summary['status']!='request_or_adapter_failed':summary['status']='conflicts_attempt_limit'
        summary.update(known_constraints_passed=False,fully_verified=False)
    if latest is not None:
        summary['last_attempt_conflicts']=len(latest['validation']['conflicts'])
    assert context==frozen, 'Host input mutated'
    summary['initial_state_mutated']=False
    write(output/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--horizon-min',type=float,default=120)
    p.add_argument('--observation-time-min',type=float,default=60)
    p.add_argument('--max-attempts',type=int,default=3)
    p.add_argument('--timeout-s',type=float,default=180)
    args=p.parse_args()
    from core301.dispatch.providers import LLMDispatchProvider
    resources,mapping=load_config()
    context=build_input(resources,mapping,load_cases(),horizon_min=args.horizon_min,observation_time_min=args.observation_time_min)
    provider=LLMDispatchProvider()
    result=asyncio.run(run_agent(provider,context,args.output,max_attempts=args.max_attempts,timeout_s=args.timeout_s))
    return 0 if result['status'] in ('all_scheduled','partial_schedule') else 1

if __name__=='__main__':raise SystemExit(main())
