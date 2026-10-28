"""Read-only complete dual-run checks; cannot resimulate, score, or submit treatment."""
import argparse
import json
import math
from pathlib import Path
from core301.dispatch.complete_contracts import CompletePlan
from .evaluation import sha,verify_rules


def verify(directory,*,require_native=True):
    d=Path(directory).resolve()
    def load(name):return json.loads((d/name).read_text())
    def lines(name):return [json.loads(x) for x in (d/name).read_text().splitlines()]
    def check(condition,message):
        if not condition:raise ValueError(message)
    hashes=load('sha256_manifest.json')
    for name,digest in hashes.items():
        path=(d/name).resolve()
        check(path.is_relative_to(d) and path.is_file() and sha(path)==digest,'SHA mismatch: '+name)
    actual={str(p.relative_to(d)) for p in d.rglob('*') if p.is_file() and p.name!='sha256_manifest.json'}
    check(set(hashes)==actual,'SHA index does not cover exact file set')
    summary=load('run_summary.json');manifest=load('run_manifest.json')
    check(not summary['failure'] and summary['endpoint_reached'],'Run incomplete')
    if require_native:check(manifest['mode']=='dual_native' and summary['real_pulse'],'Not native evidence')
    check(not manifest['real_llm'],'Unexpected LLM use')
    clock=lines('clock_trace.jsonl');events=lines('global_events.jsonl');decisions=lines('scheduling_decisions.jsonl')
    targets=[r['target_s'] for r in clock]
    check(targets==sorted(targets),'Clock went backwards')
    for row in clock:
        check(row['synchronized'] and set(row['patient_times_s'])=={'A','B'},'Incomplete barrier')
        check(all(abs(t-row['target_s'])<=1e-6 for t in row['patient_times_s'].values()),'Clock disagreement')
    check([e['sequence'] for e in events]==list(range(1,len(events)+1)),'Event order')
    check([e['global_simulation_time_s'] for e in events]==sorted(e['global_simulation_time_s'] for e in events),'Event time order')
    check(len(decisions)==3,'Unexpected scheduling attempts')
    a,blocked,recovery=decisions
    check([x['patient_label'] for x in decisions]==['A','B','B'],'Non-deterministic request order')
    check(a['result']['allocated'] and not blocked['result']['allocated'] and recovery['result']['allocated'],'Contention/recovery absent')
    conflict=blocked['result']['resource_result']['conflicts'][0]
    check(conflict['code']=='RESOURCE_IN_USE' and conflict['available_qty']==0 and conflict['required_qty']==1,'Wrong conflict')
    check(conflict['blocking_allocation_ids']==a['result']['resource_result']['allocation_ids'],'Wrong blocking allocation')
    check(blocked['request']['idempotency_key']!=recovery['request']['idempotency_key'],'Failed key reused')
    check(recovery['request']['expected_state_version']>blocked['request']['expected_state_version'],'No fresh ledger read')
    pids=[];rows_by_label={};counts={}
    for label in ('A','B'):
        prefix='patients/patient_'+label+'/'
        plan=CompletePlan.model_validate_json((d/(prefix+'complete_plan.json')).read_text())
        check(plan.run_id==summary['run_id'] and plan.patient_id==summary['run_id']+'-'+label,'Patient/run mismatch')
        rows=lines(prefix+'observations.jsonl');rows_by_label[label]=rows
        check(len(rows)==301,'Incomplete observation window')
        for t,row in zip(range(180,481),rows):
            check(abs(row['simulation_time_s']-t)<1e-6 and row['global_simulation_time_s']==t,'Sampling grid')
            check((row['run_id'],row['patient_id'],row['plan_id'])==(plan.run_id,plan.patient_id,plan.plan_id),'Observation crossed patients')
        native=load(prefix+'native_action_results.json');counts[label]=sum(x['phase']=='treatment' for x in native)
        patient=load(prefix+'patient_summary.json');pids.append(patient['worker_pid'])
        if require_native:
            commands=lines(prefix+'worker_commands.jsonl')
            check(all(c['worker_pid']==patient['worker_pid'] and c['patient_id']==plan.patient_id and c['run_id']==plan.run_id for c in commands),'Worker identity mismatch')
            treatment_commands=[c for c in commands if c['operation']=='_submit' and c['execution_identity']]
            check(len(treatment_commands)==counts[label],'Treatment transport evidence mismatch')
        if label=='A':
            receipt=load(prefix+'execution_receipt_final.json');action=receipt['actions'][0]
            check(receipt['status']=='COMPLETED' and action['delivery']['source_control_confirmed'] and action['accepted'] is True,'No confirmed native completion')
            check(abs(action['submitted_time_s']-180)<1e-6,'Illegal treatment timing')
            check(action['resource']['action_instance_id']==plan.actions[0].action_instance_id,'Receipt action identity mismatch')
            if require_native:
                evaluation=load(prefix+'evaluation_result.json')
                check(evaluation['evaluator_called'] and evaluation['computation_state']=='NOT_EVALUABLE','Evaluation evidence missing')
                check(load(prefix+'evaluation_call.json')['returncode']==0,'Evaluator process failed')
        else:
            check(not (d/(prefix+'execution_receipt.json')).exists(),'Fabricated untreated B receipt')
            check(patient['state']=='TIME_PROTOCOL_BLOCKED','B timing guard missing')
            check(rows[1]['patient_state']=='WAITING_RESOURCE','B not sampled while waiting')
            check(rows[1]['diagnostics']['diagnostic.TotalHemorrhageRate']>0,'Waiting B injury disappeared')
    check(counts=={'A':1,'B':0},'Treatment count or replay mismatch')
    if require_native:check(len(set(pids))==2 and all(isinstance(p,int) for p in pids),'Not two isolated worker processes')
    check(rows_by_label['A'][1]['diagnostics']['diagnostic.TotalHemorrhageRate']==0,'A control not confirmed independently')
    wait=[e for e in events if e['kind']=='WAIT_ENDED'];check(len(wait)==1,'Missing wait closure')
    w=wait[0];check(w['duration_s']==w['wait_end_s']-w['wait_start_s']>0,'No real nonzero wait')
    release=events[w['trigger_sequence']-1];check(release['kind']=='RESOURCE_RELEASED','Wakeup lacks release cause')
    resources=load('resource_final.json');medic=resources['resources']['medic']
    check(medic['initial_total']==1 and medic['available_qty']==1 and medic['in_use_qty']==0 and medic['reserved_qty']==0,'Resource conservation/release')
    check(not summary['unresolved_allocations'],'Unresolved allocation')
    resource_events=lines('resource_events.jsonl')
    released=[e for e in resource_events if e['operation']=='release_usage']
    check(len(released)==1 and released[0]['request']['patient_id'].endswith('-A'),'Release owner mismatch')
    check(released[0]['result']['outcome']=='SATISFIED','Release not confirmed')
    verify_rules()
    return {'status':'PASS' if require_native else 'PASS_OFFLINE_ONLY','run_id':summary['run_id'],
            'sha_files_checked':len(hashes),'worker_pids':pids,'frames_per_patient':301,
            'treatment_counts':counts,'conflict_code':conflict['code'],'waiting_duration_s':w['duration_s'],
            'waiting_status':summary['waiting_status'],'overall_status':summary['overall_status'],
            'B_later_treatment':'UNVALIDATED_TIMING','resimulation':False,'llm_calls':0}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--offline',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.directory,require_native=not a.offline),indent=2))
