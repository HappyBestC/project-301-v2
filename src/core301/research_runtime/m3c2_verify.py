"""Independent read-only causal, timing, identity and SHA verification."""
import argparse
import json
from pathlib import Path
from core301.agent.resource_feedback import parse_decision,validate_decision,authorized_observation
from core301.dispatch.complete_contracts import CompletePlan
from .evaluation import sha,verify_rules
from .m3c2_timing import protocol,VERSION

def verify(directory,require_native=True):
    d=Path(directory).resolve()
    def load(name):return json.loads((d/name).read_text())
    def lines(name):return [json.loads(x) for x in (d/name).read_text().splitlines()]
    def check(ok,reason):
        if not ok:raise ValueError(reason)
    hashes=load('sha256_manifest.json')
    check(set(hashes)=={str(p.relative_to(d)) for p in d.rglob('*') if p.is_file() and p.name!='sha256_manifest.json'},'SHA coverage')
    for name,digest in hashes.items():
        p=(d/name).resolve();check(p.is_relative_to(d) and p.is_file() and sha(p)==digest,'SHA mismatch: '+name)
    s=load('run_summary.json');m=load('run_manifest.json');timing=load('timing_protocol.json')
    check(not s['failure'] and s['endpoint_reached'],'Incomplete run')
    dynamic=m['mode']=='timing_exploratory';check(timing==protocol(dynamic),'Timing contract changed')
    if require_native:check(s['real_pulse'] and m['real_pulse'],'Not native evidence')
    if dynamic:check(load('timing_admission.json')['status']=='PASS','No independent technical admission')
    selected,waiting=s['selected_patient'],s['waiting_patient']
    check(set((selected,waiting))=={'A','B'},'Patient roles invalid')
    priority=load('priority_decision.json')['ordered_patient_ids']
    check(priority==[s['run_id']+'-'+selected,s['run_id']+'-'+waiting],'Priority role mismatch')
    decisions=lines('scheduling_decisions.jsonl');events=lines('global_events.jsonl');resource_events=lines('resource_events.jsonl')
    check([e['sequence'] for e in events]==list(range(1,len(events)+1)),'Event sequence')
    check([e['global_simulation_time_s'] for e in events]==sorted(e['global_simulation_time_s'] for e in events),'Event time reversal')
    check([x['patient_label'] for x in decisions[:2]]==[selected,waiting],'Initial request order')
    first,blocked=decisions[:2];check(first['result']['allocated'] and not blocked['result']['allocated'],'Contention absent')
    conflict=blocked['result']['resource_result']['conflicts'][0]
    check(conflict['code']=='RESOURCE_IN_USE' and conflict['blocking_allocation_ids']==first['result']['resource_result']['allocation_ids'],'Wrong actual blocker')
    feedback=lines('resource_feedback.jsonl');inputs=lines('feedback_agent_input.jsonl');parsed=lines('feedback_decisions.jsonl');raw=lines('feedback_raw_outputs.jsonl')
    requests=lines('llm_requests.jsonl');responses=lines('llm_responses.jsonl')
    check(1<=len(parsed)<=2 and len(feedback)==len(inputs)==len(parsed)==len(raw),'Decision count mismatch')
    check(s['feedback_decisions']==[x['decision_type'] for x in parsed],'Summary decision mismatch')
    if m['mode']=='feedback_native':
        check(m['real_llm'] and len(requests)==len(responses)==len(parsed),'Missing real model responses')
    else:check(not m['real_llm'] and not requests and not responses,'Fixed provider mislabeled')
    for i,(f,p,item,r) in enumerate(zip(feedback,inputs,parsed,raw)):
        dec=parse_decision(r['content']);check(dec.model_dump(mode='json')==item,'Raw decision replaced')
        validate_decision(dec,f,current_version=p['resource_snapshot']['state_version'],current_time=f['global_simulation_time_s'])
        check(p['feedback']==f and f['m2_result']==blocked['result']['resource_result'],'Feedback not actual M2 conflict')
        check(r['decision_id']==f['decision_id'],'Raw record decision identity')
        check(set(p)=={'feedback','observation','known_injuries','plan_summary','resource_snapshot','waiting_state','executed_actions','allowed_scope'},'Unexpected Agent input fields')
        check(p['known_injuries']==[{'injury_type':'external_hemorrhage','compartment':'RightLeg'}] and p['plan_summary']==[{'action_type':'control_external_bleeding','compartment':'RightLeg'}] and p['executed_actions']==[],'Agent clinical/plan grant differs')
        check(f['timing_protocol']=={'protocol_version':timing['protocol_version'],'execution_allowed_now':i==0 or dynamic,'candidate_treatment_times_s':timing['candidate_treatment_times_s']},'Timing admission misrepresented')
        check(f['allowed_operations']==(['KEEP_PLAN_AND_WAIT'] if i==0 else ['RECHECK_RESOURCES'])+['DEFER_INSUFFICIENT_EVIDENCE','STOP_UNEXECUTABLE'],'Allowed operations fabricated')
        check(f['resource_state_version'] in {e['result']['state_version'] for e in resource_events},'Snapshot version absent from real ledger')
        check(f['patient_id']==priority[1] and f['plan_id']==blocked['request']['plan_id'],'Feedback identity')
        check(f['global_simulation_time_s']==(180 if i==0 else 181),'Unexpected feedback time')
        check(not f['unresolved_execution'],'Unexpected unresolved execution in completed run')
        if requests:
            req=requests[i];res=responses[i]
            check(req['decision_id']==res['decision_id']==f['decision_id'] and req['call_index']==res['call_index']==i+1,'LLM call identity')
            check(json.loads(req['parameters']['messages'][1]['content'])==p,'Actual LLM input differs')
            check(res['response']['choices'][0]['message']['content']==r['content'],'Response replaced')
            import hashlib
            check(hashlib.sha256(req['parameters']['messages'][0]['content'].encode()).hexdigest()==req['prompt_sha256']==m['prompt_sha256'],'Prompt SHA')
            check(req['max_retries']==0 and req['timeout_s']==60 and req['parameters']['max_tokens']==1000 and req['cumulative_request_budget_units']<=24000,'Call budget exceeded')
        admitted=[e for e in events if e['kind']=='FEEDBACK_DECISION_ADMITTED' and e['decision_id']==f['decision_id']]
        check(len(admitted)==1 and admitted[0]['decision_type']==dec.decision_type,'Decision not admitted')
        kind={'KEEP_PLAN_AND_WAIT':'FEEDBACK_WAIT_REGISTERED','RECHECK_RESOURCES':'FEEDBACK_RECHECK','DEFER_INSUFFICIENT_EVIDENCE':'FEEDBACK_DEFERRED','STOP_UNEXECUTABLE':'FEEDBACK_STOPPED'}[dec.decision_type]
        applied=[e for e in events if e['kind']==kind and e['decision_id']==f['decision_id']]
        check(len(applied)==1 and applied[0]['patient_id']==priority[1],'Control differs from decision')
        if i==1:
            check(parsed[0]['decision_type']=='KEEP_PLAN_AND_WAIT','Second call without WAIT')
            trigger=events[f['trigger_event_sequence']-1]
            check(trigger['kind']=='RESOURCE_RELEASED' and trigger['patient_id']==priority[0] and trigger['state_version']==f['resource_state_version'],'Unproven wakeup')
            check(f['resource_changed'] and p['resource_snapshot']['resources']['medic']['available_qty']==1,'No resource recovery')
        else:check(p['resource_snapshot']['resources']['medic']['available_qty']==0,'Conflict input capacity incorrect')
    rechecks=sum(x['decision_type']=='RECHECK_RESOURCES' for x in parsed)
    check(len(decisions)==2+rechecks,'Unrequested resource retry')
    if rechecks:
        fresh=decisions[2]
        check(fresh['patient_label']==waiting and fresh['result']['allocated'],'RECHECK did not recover resources')
        check(fresh['request']['idempotency_key']!=blocked['request']['idempotency_key'] and fresh['request']['expected_state_version']>blocked['request']['expected_state_version'],'No fresh request/version')
    counts={};pids=[];rows_by={}
    for label in (selected,waiting):
        prefix='patients/patient_'+label+'/'
        plan=CompletePlan.model_validate_json((d/(prefix+'complete_plan.json')).read_text())
        check(plan.patient_id==s['run_id']+'-'+label and plan.run_id==s['run_id'],'Plan identity')
        check(plan.scope_id=='external_hemorrhage' and plan.severity==.4 and len(plan.actions)==1 and plan.actions[0].action_type=='control_external_bleeding' and plan.actions[0].compartment=='RightLeg','Plan scope changed')
        rows=lines(prefix+'observations.jsonl');rows_by[label]=rows
        check(len(rows)==301,'Incomplete real observations')
        patient=load(prefix+'patient_summary.json');pids.append(patient['worker_pid'])
        for time,row in zip(range(180,481),rows):
            check(abs(row['simulation_time_s']-time)<=1e-6 and row['global_simulation_time_s']==time,'Observation time')
            check(row['patient_id']==plan.patient_id and row['run_id']==s['run_id'] and row['worker_pid']==patient['worker_pid'],'Cross-patient observation')
        native=load(prefix+'native_action_results.json');treat=[a for a in native if a['phase']=='treatment'];counts[label]=len(treat)
        expected=int(label==selected or dynamic and bool(rechecks))
        check(len(treat)==expected,'Unexpected/repeated treatment')
        if require_native:
            commands=lines(prefix+'worker_commands.jsonl')
            check(all(c['run_id']==s['run_id'] and c['patient_id']==plan.patient_id and c['worker_pid']==patient['worker_pid'] for c in commands),'Worker identity')
            submissions=[c for c in commands if c['operation']=='_submit' and c['execution_identity']]
            check(len(submissions)==expected,'Native submission count')
            for c in submissions:
                allocation=first if label==selected else decisions[2];binding=c['execution_identity']
                check(binding['patient_id']==plan.patient_id and binding['plan_id']==plan.plan_id and binding['task_id']==allocation['result']['task']['task_id'] and binding['allocation_ids']==allocation['result']['resource_result']['allocation_ids'],'Treatment allocation mismatch')
        if expected:
            receipt=load(prefix+'execution_receipt_final.json');action=receipt['actions'][0];at=180 if label==selected else 181
            check(receipt['status']=='COMPLETED' and action['accepted'] is True and action['delivery']['source_control_confirmed'],'No mechanism completion')
            check(abs(action['submitted_time_s']-at)<=1e-6 and abs(treat[0]['simulation_time_s']-at)<=1e-6,'Treatment time mismatch')
            check(action['resource']['action_instance_id']==plan.actions[0].action_instance_id,'Receipt identity mismatch')
            check(rows[at+1-180]['diagnostics']['diagnostic.TotalHemorrhageRate']==0,'No independent control evidence')
            if dynamic:check(receipt['protocol_version']==VERSION and receipt['timing_protocol']['exploratory'],'Missing new protocol identity')
        else:check(not (d/(prefix+'execution_receipt.json')).exists(),'Untreated patient has receipt')
        evaluation=load(prefix+'evaluation_result.json');check(evaluation['computation_state']=='NOT_EVALUABLE' and evaluation['grade'] is None,'Unjustified formal grade')
        if dynamic:check(not evaluation['evaluator_called'],'Exploratory evidence sent as frozen evaluation')
    if require_native:check(len(set(pids))==2 and all(isinstance(p,int) for p in pids),'Not independent workers')
    for p in inputs:
        row=rows_by[waiting][int(p['feedback']['global_simulation_time_s'])-180]
        check(authorized_observation(row['patient_observation'],priority[1],row['global_simulation_time_s'])==p['observation'],'LLM observation differs from native frame')
    clock=lines('clock_trace.jsonl');check([r['target_s'] for r in clock]==sorted(r['target_s'] for r in clock),'Clock reversed')
    check(all(r['synchronized'] and set(r['patient_times_s'])=={'A','B'} and all(abs(t-r['target_s'])<=1e-6 for t in r['patient_times_s'].values()) for r in clock),'Clock desynchronized')
    releases=[e for e in resource_events if e['operation']=='release_usage']
    check(len(releases)==sum(counts.values()),'Release count')
    for release in releases:
        owner=release['request']['patient_id'];at=181 if owner==priority[0] else 182
        check(owner in priority and abs(release['request']['at_s']-at)<=1e-6 and release['result']['outcome']=='SATISFIED','Release owner/time/outcome')
    medic=load('resource_final.json')['resources']['medic']
    check(medic['initial_total']==medic['available_qty']==1 and medic['reserved_qty']==medic['in_use_qty']==0 and not s['unresolved_allocations'],'Resource conservation')
    if rechecks and not dynamic:
        blocks=[e for e in events if e['kind']=='TIME_PROTOCOL_BLOCKED'];check(len(blocks)==1 and blocks[0]['code']=='UNVALIDATED_TIMING','Frozen protocol bypass')
    verify_rules()
    return {'status':'PASS' if require_native else 'PASS_OFFLINE_ONLY','run_id':s['run_id'],'sha_files_checked':len(hashes),
        'verifier_sha256':sha(Path(__file__)),'worker_pids':pids,'treatment_counts':counts,'frames_per_patient':301,
        'actual_feedback_decisions':[x['decision_type'] for x in parsed],'real_llm_calls':len(requests),
        'feedback_status':'M3C2_REAL_AGENT_FEEDBACK_PASS' if m['mode']=='feedback_native' and require_native else 'NOT_REAL_FEEDBACK_EVIDENCE',
        'timing_status':'M3C2_TIMING_EXPLORATORY_PASS' if dynamic and require_native else 'FROZEN_TIMING_PRESERVED',
        'dual_dynamic_status':'M3C2_DUAL_PATIENT_DYNAMIC_EXECUTION_PASS' if dynamic and require_native and sum(counts.values())==2 else 'NOT_DEMONSTRATED',
        'formal_dynamic_efficacy':'M3C2_TIMING_NOT_VALIDATED'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--offline',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.directory,require_native=not a.offline),indent=2))
