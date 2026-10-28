"""M3-A: one real decision and the existing native episode, or offline validation."""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4
from core301.agent.complete_decision import agent_input, parse_decision, build_complete_plan
from core301.agent.complete_provider import LLMCompleteTreatmentProvider, PROMPT_SHA
from core301.paths import PROJECT_ROOT, PULSE_ROOT
from .runner import run as native_run, dump
from .evaluation import sha

STAGES=('LLM_CALL','DECISION_PARSE','COMPLETE_PLAN_VALIDATION','DISPATCH',
        'RESOURCE_RESERVATION','PULSE_EXECUTION','OBSERVATION','EVALUATION')


class RealWorkflow:
    def preflight(self,directory,summary,manifest):
        summary.update(mode='real_agent_native',real_llm=False,decision_id=summary['run_id']+'-decision',
                       stages={k:'NOT_RUN' for k in STAGES})
        manifest.update(mode='real_agent_native',treatment_provider='LLMCompleteTreatmentProvider',
                        prompt_sha256=PROMPT_SHA,decision_schema='301.treatment.decision.m3a.1',
                        decision_id=summary['decision_id'],llm_call_limit=1,
                        agent_authorization='M3-A synthetic clinical known RightLeg external bleeding + BASIC only',
                        catalog_sha256=sha(PROJECT_ROOT/'src/core301/dispatch/shared_resources/catalog.py'),
                        resource_costs_sha256=sha(PROJECT_ROOT/'src/core301/runtime/v2_1/resources.py'))
        try:
            self.provider=LLMCompleteTreatmentProvider()
            manifest['model']=self.provider.config.model
            # Validate native availability locally, without executing treatment or
            # making a second paid request for model discovery.
            import importlib.util
            if importlib.util.find_spec('PyPulse') is None:
                raise RuntimeError('Native Pulse binding unavailable; source scripts/activate.sh')
            if not (PULSE_ROOT/'states/StandardMale@0s.json').is_file():
                raise RuntimeError('Native initial state missing')
            dump(directory/'preflight.json',{'status':'PASS','configuration_present':True,
                 'model':self.provider.config.model,'native_binding_available':True,
                 'remote_model_availability':'checked by the sole decision request; no discovery call'})
        except Exception as exc:
            dump(directory/'preflight.json',{'status':'BLOCKED','error_type':type(exc).__name__,
                                           'reason':str(exc)})
            raise
        finally:
            dump(directory/'run_manifest.json',manifest)

    def decide(self,runtime,observation,directory,summary,manifest):
        # Registry output omits severity. This explicit clinical grant is separate
        # from simulation initialization and evaluator access.
        payload=agent_input(observation,runtime.patient_id,runtime.registry.known())
        dump(directory/'agent_input.json',payload)
        summary['stage']='LLM_CALL';summary['stages']['LLM_CALL']='RUNNING'
        content=self.provider.create_decision(payload,directory)
        summary['real_llm']=True;manifest['real_llm']=True
        summary['stages']['LLM_CALL']='PASS'
        summary['stage']='DECISION_PARSE'
        draft=parse_decision(content)
        dump(directory/'treatment_decision.json',draft.model_dump(mode='json'))
        summary['stages']['DECISION_PARSE']='PASS'
        summary['stage']='COMPLETE_PLAN_VALIDATION'
        plan=build_complete_plan(draft,runtime.run_id,runtime.patient_id)
        dump(directory/'complete_plan.json',plan.model_dump(mode='json'))
        summary['stages']['COMPLETE_PLAN_VALIDATION']='PASS'
        dump(directory/'decision_validation.json',{'status':'PASS','decision_id':summary['decision_id'],
            'plan_id':plan.plan_id,'action_instance_ids':[a.action_instance_id for a in plan.actions],
            'model_fields':['decision_type','actions.action_type','actions.compartment','reasoning_summary','refusal_reason'],
            'host_fields':['run_id','patient_id','plan_id','action_instance_id','scope_kind','scope_id','severity',
                           'location_id','execution_policy','parameter_policy','depends_on']})
        return plan

    def finalize(self,directory,summary,manifest):
        stages=summary.setdefault('stages',{k:'NOT_RUN' for k in STAGES})
        for key,flag in [('DISPATCH','resource_reservation_pass'),('RESOURCE_RESERVATION','resource_reservation_pass'),
                         ('PULSE_EXECUTION','execution_pass'),('OBSERVATION','posttreatment_observation_pass'),
                         ('EVALUATION','evaluator_called')]:
            if summary.get(flag):stages[key]='PASS'
        mapping={'dispatch':'DISPATCH','execute':'PULSE_EXECUTION','posttreatment_observations':'OBSERVATION','evaluation':'EVALUATION'}
        if summary.get('failure'):
            stage=mapping.get(summary['failure']['stage'],summary['failure']['stage'])
            if stage in stages:stages[stage]='FAILED'
            if not (directory/'decision_validation.json').exists():
                dump(directory/'decision_validation.json',{'status':'FAILED','failure':summary['failure'],
                    'decision_id':summary.get('decision_id')})
        if (directory/'dispatch_result.json').exists():
            dispatch=json.loads((directory/'dispatch_result.json').read_text())
            if not dispatch.get('allocated'):
                stages['DISPATCH']='FAILED'
                stages['RESOURCE_RESERVATION']='FAILED'
        summary['real_llm']=(directory/'llm_response.json').exists()
        summary['llm_request_attempted']=(directory/'llm_request.json').exists()
        summary['pulse_treatment_submitted']=any(a.get('phase')=='treatment' for a in json.loads((directory/'native_action_results.json').read_text()))
        summary['overall_status']=('M3A_REAL_AGENT_EXECUTION_PASS' if summary.get('real_llm') and
            all(stages[k]=='PASS' for k in STAGES) and summary.get('resource_accounting_pass') and
            not summary.get('close_error') else 'M3A_PARTIAL')
        summary['blocked']=bool(summary.get('failure'))
        manifest['real_pulse']=summary['real_pulse']
        manifest['real_llm']=summary.get('real_llm',False)
        dump(directory/'run_manifest.json',manifest)


def offline_run(output_root,run_id):
    """Explicit mock draft, no API/Pulse imports invoked and no treatment."""
    directory=Path(output_root)/run_id
    directory.mkdir(parents=True,exist_ok=False)
    mock={'schema_version':'301.treatment.decision.m3a.1','decision_type':'propose_plan',
          'actions':[{'action_type':'control_external_bleeding','compartment':'RightLeg'}],
          'reasoning_summary':'OFFLINE MOCK fixture, not an LLM response','refusal_reason':None}
    draft=parse_decision(json.dumps(mock));plan=build_complete_plan(draft,run_id,run_id+'-patient')
    dump(directory/'mock_decision.json',mock);dump(directory/'complete_plan.json',plan.model_dump(mode='json'))
    summary={'run_id':run_id,'mode':'offline_test','real_llm':False,'real_pulse':False,
             'pulse_treatment_submitted':False,'overall_status':'M3A_IMPLEMENTED_NATIVE_UNVERIFIED',
             'stages':{k:('PASS_MOCK' if k in ('DECISION_PARSE','COMPLETE_PLAN_VALIDATION') else 'NOT_RUN') for k in STAGES}}
    dump(directory/'run_summary.json',summary)
    dump(directory/'SHA256.json',{p.name:sha(p) for p in directory.iterdir() if p.is_file()})
    return directory,summary


async def run(mode='offline_test',run_id=None,output_root=None,medic_count=1):
    run_id=run_id or 'm3a-'+uuid4().hex
    if Path(run_id).name!=run_id or run_id in ('.','..'):
        raise ValueError('run_id must be one directory component')
    root=Path(output_root or PROJECT_ROOT/'experiments/results/m3a_real_treatment_agent').resolve()
    if not root.is_relative_to(PROJECT_ROOT):raise ValueError('Results must stay inside project')
    if mode=='offline_test':return offline_run(root,run_id)
    if mode!='real_agent_native':raise ValueError('Unknown mode')
    return await native_run(root,run_id,medic_count=medic_count,treatment_workflow=RealWorkflow())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['offline_test','real_agent_native'],default='offline_test')
    parser.add_argument('--run-id')
    args=parser.parse_args()
    directory,summary=asyncio.run(run(args.mode,args.run_id))
    print(json.dumps({'directory':str(directory),**summary},ensure_ascii=False,indent=2))
    return 0 if summary['overall_status'] in ('M3A_REAL_AGENT_EXECUTION_PASS','M3A_IMPLEMENTED_NATIVE_UNVERIFIED') else 1

if __name__=='__main__':raise SystemExit(main())
