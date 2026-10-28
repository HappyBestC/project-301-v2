"""Offline research fixture through existing dispatch service/provider; no Pulse/LLM calls."""
import asyncio
import json
from .demo import demo_input, demo_eta
from .models import DispatchInput, DispatchProposal
from .providers import FixedDispatchProvider
from .shared_integration import SharedDispatchCoordinator
from .shared_resources import SharedResourceManager, Plan, Action, Request, Execution, ReleaseEvidence
from .shared_resources.fixtures import research_scene


def fixture_input(patient, run_id='shared-demo'):
    data=demo_input().model_dump()
    data.update(run_id=run_id,patient_id=patient)
    data['patient_observation']['patient_id']=patient
    actions=['intubation','mechanical_ventilation']
    data['treatment_plan']={'patient_id':patient,'actions':[{'action_type':a} for a in actions]}
    for group in ('facilities','medical_teams','ambulances'):
        for asset in data[group]:
            asset['run_id']=run_id
            if 'supported_action_types' in asset:
                asset['supported_action_types']=actions
    return DispatchInput.model_validate(data)


def fixture_plan(patient, location='scene'):
    return Plan(patient_id=patient,plan_id='plan-'+patient,scope_kind='research_fixture',
        scope_id='respiratory_muscle_impairment',severity=.4,location_id=location,
        actions=(Action(action_instance_id=patient+'-int',action_type='intubation'),
                 Action(action_instance_id=patient+'-mv',action_type='mechanical_ventilation')))


def fixture_provider(patient, mode='onsite'):
    return FixedDispatchProvider(DispatchProposal(patient_id=patient,mode=mode,
        team_id='TEAM-001' if mode=='team_response' else None,
        ambulance_id='AMB-001' if mode=='evacuation' else None,
        target_facility_id='FAC-001' if mode=='evacuation' else None))


async def run_demo():
    resources=SharedResourceManager()
    stock,locations=research_scene({'medic':2,'airway_kit':2,'ventilator':1})
    resources.create_run('shared-demo',stock,locations)
    dispatch=SharedDispatchCoordinator(resources)
    dispatch.register_run('shared-demo',[fixture_input(p) for p in ('A','B')],at_s=45.,
                          patient_locations={'A':'scene','B':'scene'})
    counter=45
    def req(patient, action=None):
        nonlocal counter
        counter+=1
        return Request(run_id='shared-demo',patient_id=patient,plan_id='plan-'+patient,
            request_id=f'req-{counter}',idempotency_key=f'key-{counter}',action_instance_id=action,
            at_s=float(counter),expected_state_version=resources.get_snapshot('shared-demo')['state_version'])
    records=[]
    def show(label,result=None):
        record={'step':label,'result':result.model_dump(mode='json') if result else None,
                'snapshot':resources.get_snapshot('shared-demo')}
        records.append(record)
        print(json.dumps(record,ensure_ascii=False))
    show('initial-research-fixture')
    a=await dispatch.schedule(req('A'),fixture_plan('A'),fixture_provider('A'),demo_eta())
    assert a.allocated
    show('A-dispatch-reserved',a)
    b=await dispatch.schedule(req('B'),fixture_plan('B'),fixture_provider('B'),demo_eta())
    assert not b.allocated and any(c.code=='RESOURCE_IN_USE' for c in b.resource_result.conflicts)
    show('B-dispatch-conflict',b)
    show('A-begin-intubation',dispatch.begin_usage(req('A','A-int'),a.task.task_id))
    amounts={key:value['quantity'] for key,value in resources.get_snapshot('shared-demo')['allocations'].items()
             if value['resource_id']=='airway_kit' and value['patient_id']=='A'}
    show('A-kit-opened',resources.record_consumption(req('A','A-int'),amounts=amounts,receipt_ref='fixture:kit-opened'))
    show('A-intubation-accepted',resources.record_execution(req('A','A-int'),Execution(status='accepted',receipt_ref='fixture:intubation')))
    evidence=ReleaseEvidence(receipt_ref='fixture:stopped-detached-cleared',stopped=True,detached=True,cleared_for_reuse=True)
    show('A-intubation-ended',resources.release_usage(req('A','A-int'),evidence))
    show('A-ventilator-in-use',dispatch.begin_usage(req('A','A-mv'),a.task.task_id))
    show('A-ventilation-accepted',resources.record_execution(req('A','A-mv'),Execution(status='accepted',receipt_ref='fixture:ventilation')))
    show('A-explicit-stop-and-release',resources.release_usage(req('A','A-mv'),evidence))
    show('A-onsite-confirmed',dispatch.lifecycle(req('A'),a.task.task_id,'confirm_onsite'))
    show('A-episode-ended',dispatch.lifecycle(req('A'),a.task.task_id,'end_episode'))
    b=await dispatch.schedule(req('B'),fixture_plan('B'),fixture_provider('B'),demo_eta())
    assert b.allocated
    show('B-dispatch-retry-reserved',b)
    show('B-cancel-before-use',dispatch.lifecycle(req('B'),b.task.task_id,'cancel',detail='fixture cancellation'))
    assert resources.get_snapshot('shared-demo')['resources']['airway_kit']['consumed_qty']==1
    return records


def main():
    asyncio.run(run_demo())


if __name__=='__main__':
    main()
