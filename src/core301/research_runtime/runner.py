"""One real native episode, fixed plan/provider, existing shared resource authority."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from core301.paths import PROJECT_ROOT, PULSE_ROOT
from core301.dispatch.complete_contracts import CompletePlan, CompleteAction, CompleteDispatchInput
from core301.dispatch.shared_resources import SharedResourceManager
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.providers import FixedDispatchProvider
from core301.dispatch.models import DispatchProposal
from core301.dispatch.eta import FakeEtaProvider
from core301.pulse.observation_projector import REQUESTS, BASIC, ObservationAccess
from core301.pulse.v2.session import ResearchPulseSession, DIAGNOSTICS
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.observation_candidate_v2.projector import project, Access
from core301.observation_candidate_v2.models import EvaluationObservationV2, EvaluationFrame, ActionReceipt
from core301.contracts.observation import Measurement
from .bridge import SharedAuthority, CompleteExecutionBridge
from .evaluation import evaluate, sha, RULE_SHA, verify_rules


def dump(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def make_plan(run_id, patient_id):
    return CompletePlan(schema_version='301.treatment.complete.1',run_id=run_id,patient_id=patient_id,
        plan_id=run_id+'-plan',scope_kind='research_fixture',scope_id='external_hemorrhage',severity=.4,
        location_id='scene',execution_policy='m2a_serial_execution',parameter_policy='fixed_profile_no_overrides',
        actions=(CompleteAction(action_instance_id=run_id+'-control',action_type='control_external_bleeding',
                                compartment='RightLeg',depends_on=()),))


def dispatch_input(plan, observation):
    return CompleteDispatchInput.model_validate(dict(schema_version='301.dispatch.complete.1',
        run_id=plan.run_id,patient_id=plan.patient_id,position={'x':0,'y':0,'z':0},current_facility_id=None,
        patient_observation=observation.model_dump(),treatment_plan=plan,
        facilities=[],ambulances=[],medical_teams=[]))


class RecordedFixedProvider(FixedDispatchProvider):
    def __init__(self, patient_id, directory):
        super().__init__(DispatchProposal(patient_id=patient_id,mode='onsite',team_id=None,ambulance_id=None,target_facility_id=None))
        self.directory=directory

    async def decide_dispatch_with_resources(self, source, query_eta, shared_resources):
        dump(self.directory/'agent_received_plan.json',source.treatment_plan.model_dump(mode='json'))
        dump(self.directory/'agent_resource_view.json',shared_resources)
        return await super().decide_dispatch_with_resources(source,query_eta,shared_resources)


async def run(output_root=None, run_id=None, *, session_factory=ResearchPulseSession, medic_count=1, treatment_workflow=None):
    if session_factory is not ResearchPulseSession:
        raise ValueError('Runner requires the real ResearchPulseSession; use bridge tests for Fake sessions')
    verify_rules()
    run_id=run_id or 'closed-loop-'+uuid4().hex
    if Path(run_id).name!=run_id or run_id in ('.','..'):
        raise ValueError('run_id must be one directory component')
    directory=(Path(output_root) if output_root else PROJECT_ROOT/'experiments/results/minimal_closed_loop')/run_id
    directory=directory.resolve()
    if not directory.is_relative_to(PROJECT_ROOT):
        raise ValueError('Results must stay inside the research project')
    directory.mkdir(parents=True,exist_ok=False)  # Existing run can never replay treatment.
    patient_id=run_id+'-patient'
    plan=None if treatment_workflow else make_plan(run_id,patient_id)
    plan_id=run_id+'-plan'
    public_fields=tuple(k for k in REQUESTS if not k.startswith('neurologic.'))
    conditional=frozenset(public_fields)-frozenset(BASIC)
    access=ObservationAccess(authorized=conditional,relevant=conditional,results_obtained=conditional,
                             disclose_unavailable=conditional)
    resources=SharedResourceManager();stock,locations=research_scene({'medic':medic_count})
    resources.create_run(run_id,stock,locations)
    coordinator=SharedDispatchCoordinator(resources)
    session=session_factory(patient_id,public_fields)
    authority=SharedAuthority(plan,coordinator,session.get_simulation_time,directory) if plan else None
    runtime=CaseRuntime(patient_id,directory/'runtime',run_id=run_id,mode='research',resources=authority,
                        access=access,session=session)
    bridge=CompleteExecutionBridge(runtime,authority)
    native=session_factory is ResearchPulseSession
    summary={'run_id':run_id,'patient_id':patient_id,'plan_id':plan_id,'scenario_id':'external_rightleg04_source_control_v1',
             'overall_status':'RESEARCH_CLOSED_LOOP_V1_PARTIAL','real_pulse':False,'native_execution_requested':native,
             'execution_pass':False,'evaluator_called':False,'stage':'created','failure':None}
    rows=[];event_rows=[];frames=[];request_id=run_id+'-execute'
    if plan:dump(directory/'treatment_plan.json',plan.model_dump(mode='json'))
    for name in ('execution_events.jsonl','observations.jsonl','resource_events.jsonl'):
        (directory/name).touch()
    # Explicit initial source copies support local provenance; no historical fixture reads.
    (directory/'patient_input.json').write_bytes((PULSE_ROOT/'patients/StandardMale.json').read_bytes())
    (directory/'patient_initial_state.json').write_bytes((PULSE_ROOT/'states/StandardMale@0s.json').read_bytes())
    manifest={'run_id':run_id,'patient_id':patient_id,'scenario_id':summary['scenario_id'],
        'baseline':'301.v2.restricted.engineering.baseline.1','scope':'external_hemorrhage','severity':.4,'compartment':'RightLeg',
        'patient':'StandardMale','patient_input_sha256':sha(directory/'patient_input.json'),
        'initial_state_sha256':sha(directory/'patient_initial_state.json'),'pulse_version':'4.3.2',
        'native_library_sha256':sha(next(PULSE_ROOT.glob('PyPulse*.so'))),
        'complete_plan_version':'301.treatment.complete.1','complete_plan_sha256':sha(directory/'treatment_plan.json') if plan else None,
        'resources_version':'301.resource.m2a.1','resource_fixture':{'medic':medic_count},
        'resource_scope':'research_fixture','provider':'FixedDispatchProvider onsite','real_llm':False,
        'rule_version':'RESEARCH_RULESET_V1_LOCKED','rule_sha256':RULE_SHA,
        'timeline_s':{'injury':60,'decision':180,'endpoint':480,'sampling':1},
        'python':sys.version,'executable':sys.executable,'real_pulse':native,'observation_v2_global_activation':False}
    dump(directory/'run_manifest.json',manifest)
    def capture():
        obs=runtime.observe();t=obs.simulation_time_s;diag=session.diagnostics()
        measurements={}
        values={}
        for name in public_fields:
            group,field=name.split('.');m=getattr(getattr(obs,group,None),field,None)
            if m is not None:
                values[name]=m.value
                measurements[name]={**m.model_dump(),'unit':REQUESTS[name][2] or '1','pulse_source':list(REQUESTS[name])}
        ev=session.active_events()
        row={'run_id':run_id,'patient_id':patient_id,'plan_id':plan_id,
             'simulation_time_s':t,'patient_observation':obs.model_dump(),'measurements':measurements,
             'diagnostics':{k:{'value':diag.get(k),'status':'available' if diag.get(k) is not None else 'unavailable',
                 'observed_at_s':t,'unit':q['Unit'],'pulse_source':q} for k,q in DIAGNOSTICS},'native_events':ev}
        rows.append(row);event_rows.append({'time_s':t,'available_at_s':t,'active_events':ev})
        with (directory/'observations.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
        projected=project({'patient_id':patient_id,'time_s':t,'values':values,'diagnostics':diag},
                          Access(authorized=conditional,relevant=conditional,results_obtained=conditional,disclose_unavailable=conditional))
        frames.append(EvaluationFrame(patient=projected,diagnostics={k:Measurement(value=v,status='available' if v is not None else 'unavailable',observed_at_s=t) for k,v in diag.items()}))
        return obs
    try:
        if treatment_workflow:
            summary['stage']='preflight'
            treatment_workflow.preflight(directory,summary,manifest)
        summary['stage']='initialization'
        runtime.prepare({'patient_id':patient_id,'injuries':[{'injury_type':'external_hemorrhage','severity':.4,'compartment':'RightLeg'}]})
        summary['initialization_pass']=True
        summary['real_pulse']=native
        (directory/'pretreatment_state.json').write_text(session.serialize_state())
        before=capture();summary['pretreatment_observation_pass']=True
        if treatment_workflow:
            plan=treatment_workflow.decide(runtime,before,directory,summary,manifest)
            plan=CompletePlan.model_validate(plan)
            if (plan.run_id,plan.patient_id,plan.plan_id)!=(run_id,patient_id,plan_id):
                raise ValueError('Treatment workflow identity mismatch')
            authority=SharedAuthority(plan,coordinator,session.get_simulation_time,directory)
            runtime.resources=authority
            bridge=CompleteExecutionBridge(runtime,authority)
            dump(directory/'treatment_plan.json',plan.model_dump(mode='json'))
            manifest['complete_plan_sha256']=sha(directory/'treatment_plan.json')
            dump(directory/'run_manifest.json',manifest)
        source=dispatch_input(plan,before);dump(directory/'dispatch_input.json',source.model_dump(mode='json'))
        coordinator.register_run(run_id,[source],at_s=float(session.get_simulation_time()),patient_locations={patient_id:'scene'})
        summary['stage']='dispatch'
        req=authority.request('schedule')
        result=await coordinator.schedule_complete(req,plan,RecordedFixedProvider(patient_id,directory),FakeEtaProvider({}))
        dump(directory/'dispatch_result.json',result.model_dump(mode='json'))
        if not result.allocated or result.resource_result.outcome!='SATISFIED':
            raise RuntimeError('Resource dispatch not satisfied; no Pulse treatment submitted')
        authority.task_id=result.task.task_id
        # Same logical request returns same task/reservation without a second decision.
        duplicate=await coordinator.schedule_complete(req,plan,RecordedFixedProvider(patient_id,directory),FakeEtaProvider({}))
        if duplicate.task.task_id!=result.task.task_id:raise RuntimeError('Dispatch replay mismatch')
        summary['resource_reservation_pass']=True
        context=runtime.build_context()
        summary['stage']='execute'
        record=bridge.execute(plan,request_id=request_id,context_ref=context.context_ref)
        dump(directory/'execution_receipt.json',record)
        first_count=len(session.action_results)
        repeated=bridge.execute(plan,request_id=request_id,context_ref=context.context_ref)
        if repeated!=record or len(session.action_results)!=first_count:raise RuntimeError('Execution replay was not idempotent')
        summary['execution_accepted']=record['actions'][0]['accepted'] is True
        summary['stage']='posttreatment_observations'
        for _ in range(300):
            runtime.advance(1.0);capture()
        record=runtime.query(request_id);dump(directory/'execution_receipt_final.json',record)
        (directory/'final_state.json').write_text(session.serialize_state())
        authority.finish(record)
        for operation in ('confirm_onsite','end_episode'):
            outcome=coordinator.lifecycle(authority.request(operation),authority.task_id,operation)
            authority.require(outcome.resource_result)
        summary['execution_pass']=record['status']=='COMPLETED'
        summary['resource_accounting_pass']=resources.get_snapshot(run_id)['resources']['medic']['available_qty']==medic_count
        summary['posttreatment_observation_pass']=len(rows)==301
        dump(directory/'native_events.json',{'complete':False,'sampling_s':1,'coverage_s':[rows[0]['simulation_time_s'],rows[-1]['simulation_time_s']],
                                            'records':event_rows,'limitation':'1s snapshots; not claimed complete 0.02s transition history'})
        evaluation_obs=EvaluationObservationV2(patient_id=patient_id,evidence_path=str(directory.relative_to(PROJECT_ROOT)),
            frames=frames,events=[],actions=[ActionReceipt(observed_at_s=a['submitted_time_s'],phase='treatment',state=a['state']) for a in record['actions']],
            source_snapshots=[],gaps=['Event transitions not reconstructed from 1s snapshots; raw snapshots separate',
            'No matched control; no independent Soldier evidence contract; only 13 public fields requested'])
        dump(directory/'evaluation_observation.json',evaluation_obs.model_dump(mode='json'))
        summary['stage']='evaluation'
        evaluation=evaluate(directory,plan,float(session.get_simulation_time()))
        dump(directory/'evaluation_result.json',evaluation)
        summary.update(evaluator_called=evaluation['evaluator_called'],evaluation_state=evaluation['computation_state'],
                       physiological_grade=None,stage='completed',simulation_time_s=float(session.get_simulation_time()))
        if native and all(summary[k] for k in ('execution_pass','resource_accounting_pass','posttreatment_observation_pass','evaluator_called')):
            summary['overall_status']='RESEARCH_CLOSED_LOOP_V1_PASS'
    except Exception as exc:
        summary['failure']={'type':type(exc).__name__,'message':str(exc),'stage':summary['stage']}
        # Preserve genuine incomplete/unknown evidence. Never manufacture a grade or release.
    finally:
        dump(directory/'native_action_results.json',session.action_results)
        dump(directory/'resource_final.json',resources.get_snapshot(run_id))
        with (directory/'resource_events.jsonl').open('w') as f:
            for event in resources.get_events(run_id):f.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n')
        try:runtime.close()
        except Exception as exc:summary['close_error']=str(exc);summary['overall_status']='RESEARCH_CLOSED_LOOP_V1_PARTIAL'
        if not (directory/'evaluation_result.json').exists():
            dump(directory/'evaluation_result.json',{'run_id':run_id,'patient_id':patient_id,'plan_id':plan_id,
                'evaluator_called':False,'computation_state':'NOT_RUN','grade':None,
                'reason':summary['failure'] or {'stage':summary['stage']}})
        if treatment_workflow:treatment_workflow.finalize(directory,summary,manifest)
        dump(directory/'run_summary.json',summary)
        dump(directory/'SHA256.json',{str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    return directory,summary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-id');args=parser.parse_args()
    directory,summary=asyncio.run(run(run_id=args.run_id))
    print(json.dumps({'directory':str(directory),**summary},ensure_ascii=False,indent=2))
    return 0 if summary['overall_status']=='RESEARCH_CLOSED_LOOP_V1_PASS' else 1

if __name__=='__main__':raise SystemExit(main())
