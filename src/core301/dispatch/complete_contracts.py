"""M2-C complete research plans; old frozen contracts are unchanged.

Business parameters are side/compartment. Native doses/settings remain owned by
fixed profile executors; extra parameter overrides are rejected, never discarded.
"""
from functools import lru_cache, partial
from typing import Literal
from pydantic import model_validator
from pydantic_core import PydanticCustomError
from .shared_resources.models import Action, Plan, ID
from .shared_resources.catalog import Catalog
from .models import DispatchInput, Facility, MedicalTeam
from .validation import validate_proposal

PLAN_VERSION = '301.treatment.complete.1'
DISPATCH_VERSION = '301.dispatch.complete.1'
ACTION_TYPES = ('control_external_bleeding','fluid_resuscitation','transfusion',
    'control_internal_bleeding','occlusive_dressing','needle_decompression',
    'control_hemothorax_bleeding','chest_tube','intubation','mechanical_ventilation',
    'supplemental_oxygen','remove_from_exposure')
ActionType = Literal[*ACTION_TYPES]


@lru_cache(maxsize=1)
def catalog():
    return Catalog()


class CompleteAction(Action):
    action_type: ActionType
    # Exact serial execution dependencies, not invented clinical dependencies.
    depends_on: tuple[ID, ...]


class CompletePlan(Plan):
    schema_version: Literal['301.treatment.complete.1']
    run_id: ID
    actions: tuple[CompleteAction, ...]
    execution_policy: Literal['m2a_serial_execution']
    parameter_policy: Literal['fixed_profile_no_overrides']

    def to_resource_plan(self):
        data={name:getattr(self,name) for name in Plan.model_fields if name!='actions'}
        data['actions']=tuple(Action(**{name:getattr(a,name) for name in Action.model_fields}) for a in self.actions)
        return Plan(**data)

    @model_validator(mode='after')
    def complete_semantics(self):
        for index,a in enumerate(self.actions):
            expected=() if index==0 else (self.actions[index-1].action_instance_id,)
            if a.depends_on!=expected:
                raise PydanticCustomError('DEPENDENCY_UNMET','Dependencies must preserve the M2-A serial execution chain')
        error=catalog().validate_scope(self.to_resource_plan())
        if error:
            raise PydanticCustomError(error[0],error[1])
        return self


class CompleteFacility(Facility):
    supported_action_types: list[ActionType]


class CompleteMedicalTeam(MedicalTeam):
    supported_action_types: list[ActionType]


class CompleteDispatchInput(DispatchInput):
    schema_version: Literal['301.dispatch.complete.1']
    treatment_plan: CompletePlan
    facilities: list[CompleteFacility]
    medical_teams: list[CompleteMedicalTeam]

    @model_validator(mode='after')
    def complete_identity(self):
        if self.run_id!=self.treatment_plan.run_id:
            raise ValueError('cross-run complete plan')
        return self


def decode_dispatch_input(value):
    data=value.model_dump() if hasattr(value,'model_dump') else value
    if not isinstance(data,dict):
        raise ValueError('dispatch input must be an object')
    if 'schema_version' not in data:
        return DispatchInput.model_validate(data)
    if data['schema_version']!=DISPATCH_VERSION:
        raise ValueError('CONTRACT_VERSION_UNSUPPORTED')
    return CompleteDispatchInput.model_validate(data)


def required_actions(plan):
    return frozenset(a.action_type for a in CompletePlan.model_validate(plan).actions)


validate_complete_proposal=partial(validate_proposal, input_model=CompleteDispatchInput,
                                  required_actions=required_actions, action_types=ACTION_TYPES)


def from_resource_plan(run_id, plan):
    """Explicit backend bridge. Validate existing scope; never repair/reorder input."""
    plan=Plan.model_validate(plan)
    actions=tuple(CompleteAction(**a.model_dump(),depends_on=() if i==0 else (plan.actions[i-1].action_instance_id,))
                  for i,a in enumerate(plan.actions))
    return CompletePlan(**{**plan.model_dump(),'actions':actions},schema_version=PLAN_VERSION,
                        run_id=run_id,execution_policy='m2a_serial_execution',parameter_policy='fixed_profile_no_overrides')


def from_legacy_plan(run_id, plan, *, plan_id, action_instance_ids, scope_kind, scope_id, severity, location_id):
    """No inferred scope/IDs. Existing legal V1 plans may still fail research admission."""
    from core301.contracts.treatment import TreatmentPlan
    plan=TreatmentPlan.model_validate(plan)
    if len(action_instance_ids)!=len(plan.actions):
        raise ValueError('exact action instance IDs required')
    actions=tuple(Action(action_instance_id=identifier,**a.model_dump()) for identifier,a in zip(action_instance_ids,plan.actions))
    return from_resource_plan(run_id,Plan(patient_id=plan.patient_id,plan_id=plan_id,actions=actions,
        scope_kind=scope_kind,scope_id=scope_id,severity=severity,location_id=location_id))


def to_legacy_plan(plan):
    """Explicit rejection: complete metadata has no lossless V1 representation."""
    CompletePlan.model_validate(plan)
    raise ValueError('LOSSY_CONVERSION: V1 cannot retain instance IDs, dependencies, scope and policy')
