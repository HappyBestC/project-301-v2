"""Complete fixed-profile fixture -> existing Agent entry -> shared coordinator."""
import asyncio
import json
from .complete_contracts import CompleteDispatchInput, from_resource_plan, DISPATCH_VERSION
from .shared_resources import Plan, Action, SharedResourceManager, Request
from .shared_resources.catalog import Catalog
from .shared_resources.fixtures import research_scene
from .shared_integration import SharedDispatchCoordinator
from .shared_demo import fixture_input, fixture_provider
from .demo import demo_eta


def research_plan(scope, patient='A', run_id='complete-demo', *, blood=False):
    """Build deterministic known research sequences; not a Treatment Agent."""
    c=Catalog()
    if scope in c.composites:
        p=c.composites[scope]
        kinds=p['treatment_bundles']['A']+p['treatment_bundles']['B']
        severity=None
    else:
        p=c.singles[scope]
        # Whitelists are not ordered plans. Select the existing tested branch,
        # before constructing the input plan; no incoming plan is reordered.
        kinds=[k for k in p['actions'] if k!=('fluid_resuscitation' if blood else 'transfusion')]
        kinds=sorted(kinds,key=lambda k:0 if k.startswith('control_') or k=='intubation' else 1)
        severity=p.get('severity_levels',[None])[0]
    actions=tuple(Action(action_instance_id=f'{patient}-{i}',action_type=k,
        side='Left' if k in ('occlusive_dressing','needle_decompression','chest_tube','control_hemothorax_bleeding') else None,
        compartment={'control_external_bleeding':'RightLeg','control_internal_bleeding':'Spleen'}.get(k)) for i,k in enumerate(kinds))
    return from_resource_plan(run_id,Plan(patient_id=patient,plan_id='plan-'+patient,scope_kind='research_fixture',
                           scope_id=scope,severity=severity,location_id='scene',actions=actions))


def research_input(plan):
    data=fixture_input(plan.patient_id,plan.run_id).model_dump()
    data.update(schema_version=DISPATCH_VERSION,treatment_plan=plan)
    # Explicit independent fixture assets, not inferred real qualifications.
    for r in data['facilities']+data['medical_teams']:
        r['supported_action_types']=list(Catalog().requirements)
    return CompleteDispatchInput.model_validate(data)


async def run_demo():
    plans=[research_plan('penetrating_thoracic_composite_v2',p) for p in ('A','B')]
    c=Catalog(); resources=SharedResourceManager()
    stock,locations=research_scene({k:1 for k in c.resources})
    resources.create_run('complete-demo',stock,locations)
    dispatch=SharedDispatchCoordinator(resources)
    dispatch.register_run('complete-demo',[research_input(p) for p in plans],at_s=45.,
                          patient_locations={'A':'scene','B':'scene'})
    records=[]
    for index,plan in enumerate(plans):
        before=resources.get_snapshot('complete-demo')
        req=Request(run_id='complete-demo',patient_id=plan.patient_id,plan_id=plan.plan_id,
            request_id='req-'+plan.patient_id,idempotency_key='key-'+plan.patient_id,action_instance_id=None,
            at_s=46.+index,expected_state_version=before['state_version'])
        seen=[]
        class Capture:
            async def decide_dispatch_with_resources(self,source,query,view):
                seen.append(source.treatment_plan.model_dump(mode='json'))
                assert source.treatment_plan==plan
                assert not view['constraints']['unsupported_dispatch_actions']
                return await fixture_provider(plan.patient_id).decide_dispatch_with_resources(source,query,view)
        result=await dispatch.schedule_complete(req,plan,Capture(),demo_eta())
        assert seen==[plan.model_dump(mode='json')]
        assert result.allocated==(index==0)
        record={'input_plan':plan.model_dump(mode='json'),'agent_received_plan':seen[0],
                'result':result.model_dump(mode='json'),'before':before,'after':resources.get_snapshot('complete-demo')}
        records.append(record); print(json.dumps(record,ensure_ascii=False))
    return records


def main(): asyncio.run(run_demo())


if __name__=='__main__': main()
