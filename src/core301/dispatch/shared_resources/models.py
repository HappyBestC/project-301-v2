"""M2-A versioned backend contracts; quantities are integer research tokens only."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError('blank identifier')
    return value


ID = Annotated[str, AfterValidator(nonblank)]
Count = Annotated[int, Field(strict=True, ge=0)]
Time = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, revalidate_instances='always')


class Request(Model):
    run_id: ID
    patient_id: ID
    plan_id: ID
    request_id: ID
    idempotency_key: ID
    action_instance_id: ID | None
    at_s: Time
    expected_state_version: Count


class Resource(Model):
    resource_id: ID
    resource_type_id: ID
    unit: ID
    use_mode: Literal['consumable', 'reusable']
    initial_total: Count | None
    location_id: ID | None
    scope_kind: Literal['research_fixture']


class Location(Model):
    location_id: ID
    capabilities: frozenset[str] | None
    permissions: frozenset[str] | None
    protected_route_available: bool | None = None
    receiving_environment_verified: bool | None = None


class Action(Model):
    action_instance_id: ID
    action_type: ID
    side: Literal['Left', 'Right'] | None = None
    compartment: ID | None = None


class Plan(Model):
    patient_id: ID
    plan_id: ID
    scope_kind: Literal['research_fixture', 'clinical_design']
    scope_id: ID
    severity: float | None = Field(default=None, allow_inf_nan=False)
    location_id: ID | None
    actions: tuple[Action, ...]

    @model_validator(mode='after')
    def unique_actions(self):
        if not self.actions or len({a.action_instance_id for a in self.actions}) != len(self.actions):
            raise ValueError('nonempty unique action instances required')
        return self


class Execution(Model):
    status: Literal['accepted', 'rejected', 'unknown']
    receipt_ref: ID


class ReleaseEvidence(Model):
    receipt_ref: ID
    stopped: bool
    detached: bool
    cleared_for_reuse: bool


class ResourceChange(Model):
    resource_id: ID
    kind: Literal['fault', 'unavailable', 'restore', 'move', 'receive', 'lose']
    reason: ID
    receipt_ref: ID
    quantity: Count | None = None
    location_id: ID | None = None

    @model_validator(mode='after')
    def fields(self):
        if self.kind in ('receive', 'lose'):
            if self.quantity is None or self.quantity == 0:
                raise ValueError('positive quantity required')
        elif self.quantity is not None:
            raise ValueError('quantity applies only to receive/lose')
        if self.kind != 'move' and self.location_id is not None:
            raise ValueError('location_id applies only to move')
        return self


class Conflict(Model):
    code: str
    run_id: str
    patient_id: str
    plan_id: str
    action_instance_id: str | None
    action_type: str | None = None
    requirement_id: str | None = None
    resource_id: str | None = None
    resource_type_id: str | None = None
    required_qty: int | None = None
    available_qty: int | None = None
    unit: str | None = None
    blocking_allocation_ids: tuple[str, ...] = ()
    state_version: int
    detail: str
    evidence_refs: tuple[str, ...] = ()


class Result(Model):
    schema_version: Literal['301.resource.m2a.1'] = '301.resource.m2a.1'
    run_id: str
    patient_id: str
    plan_id: str
    request_id: str
    state_version: int
    outcome: Literal['SATISFIED', 'UNSATISFIED', 'INDETERMINATE']
    conflicts: tuple[Conflict, ...] = ()
    allocation_ids: tuple[str, ...] = ()
    affected_allocation_ids: tuple[str, ...] = ()
