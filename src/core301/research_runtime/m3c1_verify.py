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
    decision=load('priority_decision.json');payload=load('priority_agent_input.json')
    from core301.agent.priority_decision import parse_decision,validate_decision
    parsed=parse_decision(load('priority_raw_output.json')['content'])
    check(parsed.model_dump(mode='json')==decision,'Raw priority replaced')
    validate_decision(parsed,payload,current_time=180.,current_version=payload['resource_snapshot']['state_version'])
    selected,waiting=[pid.rsplit('-',1)[-1] for pid in parsed.ordered_patient_ids]
    check(set((selected,waiting))=={'A','B'},'Invalid patient identities')
    if manifest['priority_mode']=='llm_priority':
        request=load('llm_request.json');response=load('llm_response.json')['response']
        check(manifest['real_llm'] and summary['real_llm'],'Missing real LLM evidence')
        check(response['choices'][0]['message']['content']==load('priority_raw_output.json')['content'],'Model output replaced')
        check(json.loads(request['parameters']['messages'][1]['content'])==payload,'Request input differs')
        check(request['max_retries']==0 and request['timeout_s']==60,'Unbounded call')
        import hashlib
        check(hashlib.sha256(request['parameters']['messages'][0]['content'].encode()).hexdigest()==manifest['prompt_sha256']==request['prompt_sha256'],'Prompt SHA mismatch')
    else:
        check(not manifest['real_llm'],'Fixed mislabeled as LLM')
        check(selected==('A' if manifest['priority_mode']=='fixed_A_first' else 'B'),'Wrong baseline order')
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
    check([x['patient_label'] for x in decisions]==[selected,waiting,waiting],'Request order differs from priority decision')
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
            for command in treatment_commands:
                binding=command['execution_identity']
                check(binding['patient_id']==plan.patient_id and binding['plan_id']==plan.plan_id and binding['run_id']==plan.run_id,'Treatment binding crossed patients')
                check(binding['allocation_ids']==a['result']['resource_result']['allocation_ids'] and binding['task_id']==a['result']['task']['task_id'],'Treatment lacks winning allocation')
        if label==selected:
            receipt=load(prefix+'execution_receipt_final.json');action=receipt['actions'][0]
            check(receipt['status']=='COMPLETED' and action['delivery']['source_control_confirmed'] and action['accepted'] is True,'No confirmed native completion')
            check(abs(action['submitted_time_s']-180)<1e-6,'Illegal treatment timing')
            check(action['resource']['action_instance_id']==plan.actions[0].action_instance_id,'Receipt action identity mismatch')
            if require_native:
                evaluation=load(prefix+'evaluation_result.json')
                check(evaluation['evaluator_called'] and evaluation['computation_state']=='NOT_EVALUABLE','Evaluation evidence missing')
                check(load(prefix+'evaluation_call.json')['returncode']==0,'Evaluator process failed')
        else:
            check(not (d/(prefix+'execution_receipt.json')).exists(),'Fabricated waiting-patient receipt')
            check(patient['state']=='TIME_PROTOCOL_BLOCKED','Waiting-patient timing guard missing')
            check(rows[1]['patient_state']=='WAITING_RESOURCE','Waiting patient not sampled')
            check(rows[1]['diagnostics']['diagnostic.TotalHemorrhageRate']>0,'Waiting patient injury disappeared')
    check(counts=={selected:1,waiting:0},'Treatment count or replay mismatch')
    if require_native:check(len(set(pids))==2 and all(isinstance(p,int) for p in pids),'Not two isolated worker processes')
    check(rows_by_label[selected][1]['diagnostics']['diagnostic.TotalHemorrhageRate']==0,'Selected patient control not confirmed independently')
    wait=[e for e in events if e['kind']=='WAIT_ENDED'];check(len(wait)==1,'Missing wait closure')
    w=wait[0];check(w['duration_s']==w['wait_end_s']-w['wait_start_s']>0,'No real nonzero wait')
    release=events[w['trigger_sequence']-1];check(release['kind']=='RESOURCE_RELEASED','Wakeup lacks release cause')
    resources=load('resource_final.json');medic=resources['resources']['medic']
    check(medic['initial_total']==1 and medic['available_qty']==1 and medic['in_use_qty']==0 and medic['reserved_qty']==0,'Resource conservation/release')
    check(not summary['unresolved_allocations'],'Unresolved allocation')
    resource_events=lines('resource_events.jsonl')
    released=[e for e in resource_events if e['operation']=='release_usage']
    check(len(released)==1 and released[0]['request']['patient_id'].endswith('-'+selected),'Release owner mismatch')
    check(released[0]['result']['outcome']=='SATISFIED','Release not confirmed')
    # Reconstruct authorized five-metric inputs from the actual pre-treatment frames.
    from core301.agent.complete_decision import agent_input
    for item in payload['patients']:
        label=item['patient_id'].rsplit('-',1)[-1]
        source=rows_by_label[label][0]['patient_observation']
        projected=agent_input(source,item['patient_id'],item['known_injuries'])
        projected.pop('schema_version');projected.pop('allowed_actions')
        from core301.dispatch.complete_contracts import catalog
        plan=CompletePlan.model_validate_json((d/('patients/patient_'+label+'/complete_plan.json')).read_text())
        projected['plan_summary']=[{'action_type':act.action_type,'compartment':act.compartment,
            'required_resources':dict(catalog().requirements[act.action_type].holds+catalog().requirements[act.action_type].stock)} for act in plan.actions]
        check(projected==item,'Agent authorized projection differs from Pulse/plan')
    first=a['request']
    check(first['expected_state_version']==payload['resource_state_version'],'Decision used stale ledger')
    check(released[0]['request']['at_s']>=181 and released[0]['request']['at_s']<181.000001,'Release time changed')
    check(not any(e['kind']=='TREATMENT_STARTED' and e['patient_id'].endswith('-'+waiting) for e in events),'Waiting patient executed')
    timing=[e for e in events if e['kind']=='TIME_PROTOCOL_BLOCKED']
    check(len(timing)==1 and timing[0]['code']=='UNVALIDATED_TIMING' and timing[0]['global_simulation_time_s']==181 and timing[0]['patient_id']==parsed.ordered_patient_ids[1],'Frozen timing guard evidence missing')
    snapshot=payload['resource_snapshot']
    check(snapshot['run_id']==summary['run_id'] and not snapshot['allocations'] and not snapshot['plans'],'Invalid initial ledger snapshot')
    check(snapshot['resources']['medic']['available_qty']==1 and snapshot['resources']['medic']['reserved_qty']==0 and snapshot['resources']['medic']['in_use_qty']==0,'Wrong decision resource availability')
    verify_rules()
    return {'status':'PASS' if require_native else 'PASS_OFFLINE_ONLY','run_id':summary['run_id'],
            'verifier_sha256':sha(Path(__file__)),'sha_files_checked':len(hashes),'worker_pids':pids,'frames_per_patient':301,
            'treatment_counts':counts,'conflict_code':conflict['code'],'waiting_duration_s':w['duration_s'],
            'waiting_status':summary['waiting_status'],'overall_status':summary['overall_status'],
            'waiting_patient':waiting,'selected_patient':selected,'later_treatment':'UNVALIDATED_TIMING','resimulation':False,'llm_calls':int(manifest['real_llm'])}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--offline',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.directory,require_native=not a.offline),indent=2))
