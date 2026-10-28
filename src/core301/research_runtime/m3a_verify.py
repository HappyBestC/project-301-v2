"""Read-only M3-A provenance verification; no model calls or native execution."""
import argparse
import json
from pathlib import Path
from core301.agent.complete_decision import agent_input, parse_decision, build_complete_plan
from core301.agent.complete_provider import PROMPT, PROMPT_SHA
from .verify import verify as verify_native


def verify(directory):
    directory=Path(directory)
    native=verify_native(directory)
    def load(name):return json.loads((directory/name).read_text())
    manifest=load('run_manifest.json');summary=load('run_summary.json')
    if manifest['mode']!='real_agent_native' or not manifest['real_llm'] or not summary['real_pulse']:
        raise ValueError('Not a real-agent native run')
    response=load('llm_response.json')['response']
    content=response['choices'][0]['message']['content']
    draft=parse_decision(content)
    if draft.model_dump(mode='json')!=load('treatment_decision.json'):
        raise ValueError('Parsed decision differs from raw response')
    plan=build_complete_plan(draft,manifest['run_id'],manifest['patient_id'])
    for name in ('complete_plan.json','treatment_plan.json','agent_received_plan.json'):
        if load(name)!=plan.model_dump(mode='json'):raise ValueError('Model decision changed: '+name)
    first=json.loads((directory/'observations.jsonl').read_text().splitlines()[0])
    known=[{'injury_type':'external_hemorrhage','compartment':'RightLeg'}]
    expected=agent_input(first['patient_observation'],manifest['patient_id'],known)
    if expected!=load('agent_input.json'):raise ValueError('Input not derived from recorded observation')
    request=load('llm_request.json')
    messages=request['parameters']['messages']
    if messages!=[{'role':'system','content':PROMPT},
                  {'role':'user','content':json.dumps(expected,ensure_ascii=False,allow_nan=False)}]:
        raise ValueError('Recorded request messages differ from actual authorized input/Prompt')
    if request['prompt_sha256']!=PROMPT_SHA or manifest['prompt_sha256']!=PROMPT_SHA:
        raise ValueError('Prompt SHA mismatch')
    if request['max_retries']!=0 or manifest['llm_call_limit']!=1:
        raise ValueError('Unbounded call policy')
    validation=load('decision_validation.json')
    if validation['decision_id']!=manifest['decision_id'] or validation['plan_id']!=plan.plan_id:
        raise ValueError('Decision/plan identity mismatch')
    if validation['action_instance_ids']!=[a.action_instance_id for a in plan.actions]:
        raise ValueError('Decision/action identity mismatch')
    if summary['overall_status']!='M3A_REAL_AGENT_EXECUTION_PASS' or set(summary['stages'].values())!={'PASS'}:
        raise ValueError('Incomplete stages')
    return {**native,'decision_provenance':'PASS','model_requested':request['parameters']['model'],
            'model_reported':response['model'],'usage':response.get('usage'),
            'input_measurements':list(expected['measurements']),
            'decision_id':manifest['decision_id'],'action':draft.actions[0].model_dump(),
            'scope_limitation':'Single candidate wiring validation; not complex planning or two real LLM agents'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory')
    args=parser.parse_args()
    print(json.dumps(verify(args.directory),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
