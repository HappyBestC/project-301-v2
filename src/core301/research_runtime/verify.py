"""Read-only checks of one exported run; does not rescore efficacy or run Pulse."""
import argparse
import json
import math
from pathlib import Path
from .evaluation import sha,verify_rules
from core301.dispatch.complete_contracts import CompletePlan
from core301.observation_candidate_v2.models import EvaluationObservationV2


def verify(directory):
    d=Path(directory);hashes=json.loads((d/'SHA256.json').read_text())
    for relative,digest in hashes.items():
        path=(d/relative).resolve()
        if not path.is_relative_to(d.resolve()) or sha(path)!=digest:
            raise ValueError('Export SHA mismatch: '+relative)
    load=lambda name:json.loads((d/name).read_text())
    plan=CompletePlan.model_validate_json((d/'treatment_plan.json').read_text())
    if load('agent_received_plan.json')!=plan.model_dump(mode='json'):raise ValueError('Plan transport changed')
    obs=[json.loads(x) for x in (d/'observations.jsonl').read_text().splitlines()]
    times=[x['simulation_time_s'] for x in obs]
    if len(times)!=301 or not math.isclose(times[0],180,abs_tol=1e-6) or not math.isclose(times[-1],480,abs_tol=1e-6):
        raise ValueError('Incomplete observation window')
    if any(not math.isclose(b-a,1,abs_tol=1e-6) for a,b in zip(times,times[1:])):raise ValueError('Invalid sample grid')
    if any((x['run_id'],x['patient_id'],x['plan_id'])!=(plan.run_id,plan.patient_id,plan.plan_id) for x in obs):raise ValueError('Observation identity')
    tail=[x for x in obs if x['simulation_time_s']>=420-1e-6]
    if len(tail)!=61:raise ValueError('Incomplete tail window')
    receipt=load('execution_receipt_final.json');action=receipt['actions'][0]
    if receipt['status']!='COMPLETED' or action['accepted'] is not True or not action['delivery']['source_control_confirmed']:
        raise ValueError('No native source-control completion')
    if action['resource']['action_instance_id']!=plan.actions[0].action_instance_id:raise ValueError('Action mapping')
    treatment=[x for x in load('native_action_results.json') if x['phase']=='treatment']
    if len(treatment)!=1:raise ValueError('Treatment replay')
    resources=load('resource_final.json')
    for r in resources['resources'].values():
        if r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty']!=r['total_qty']:raise ValueError('Total conservation')
        if r['available_qty']+r['reserved_qty']+r['in_use_qty']+r['unavailable_qty']!=r['total_qty']:raise ValueError('State conservation')
    if resources['resources']['medic']['available_qty']!=1:raise ValueError('Medic not returned')
    if not set(action['resource']['allocation_ids'])<=set(resources['allocations']):raise ValueError('Allocation mapping')
    EvaluationObservationV2.model_validate_json((d/'evaluation_observation.json').read_text())
    call=load('evaluation_call.json');result=load('evaluation_result.json');raw=load('evaluator_stdout.json')
    if call['returncode']!=0 or call['manifest_sha256']!=sha(d/'evaluation_manifest.json'):raise ValueError('Evaluation invocation')
    if result['raw_evaluator_result']!=raw or raw['computation_state']!='NOT_EVALUABLE' or raw['formal_grade'] is not None:raise ValueError('Evaluation changed')
    if result['run_id']!=plan.run_id or result['plan_id']!=plan.plan_id:raise ValueError('Evaluation identity')
    verify_rules()
    return {'status':'PASS','run_id':plan.run_id,'sha_files_checked':len(hashes),'frames':len(times),'tail_frames':len(tail),
            'native_treatment_count':len(treatment),'evaluation_state':raw['computation_state'],
            'evaluation_errors':raw['errors'],'resimulation':False,'efficacy_rescoring':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
    print(json.dumps(verify(a.directory),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
