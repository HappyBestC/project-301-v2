"""MR5 exact payload fields. Nullable keys are required; no implicit defaults."""
from typing import Annotated, Generic, Literal, TypeVar
from pydantic import AfterValidator, Field, model_validator
from core301.contracts.base import Contract, Number, Time
from core301.contracts.observation import PatientObservation
from core301.contracts.treatment import ACTION_TYPES, TreatmentPlan


def nonblank(value):
    if not value.strip():
        raise ValueError("identifier or text must not be blank")
    return value


ID = Annotated[str, AfterValidator(nonblank)]
ActionType = Literal[*ACTION_TYPES]
Mode = Literal["onsite", "team_response", "evacuation"]
TaskState = Literal["assigned", "to_patient", "at_patient", "transporting", "at_facility", "completed", "failed", "cancelled"]
Leg = Literal["team_to_patient", "ambulance_to_patient", "patient_to_facility"]
ENDED = frozenset(("completed", "failed", "cancelled"))


def unique(items, name):
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {name}")


class Position(Contract):
    x: Number
    y: Number
    z: Number


class Facility(Contract):
    run_id: ID
    facility_id: ID
    display_name: ID
    kind: Literal["hospital", "aid_station"]
    position: Position
    capacity: Annotated[int, Field(ge=0)]
    supported_action_types: list[ActionType]
    reserved_patient_ids: list[ID]
    admitted_patient_ids: list[ID]

    @model_validator(mode="after")
    def consistent(self):
        for field in ("supported_action_types", "reserved_patient_ids", "admitted_patient_ids"):
            unique(getattr(self, field), field)
        if set(self.reserved_patient_ids) & set(self.admitted_patient_ids):
            raise ValueError("reserved and admitted patients overlap")
        if self.remaining_capacity < 0:
            raise ValueError("facility capacity exceeded")
        return self

    @property
    def remaining_capacity(self):
        return self.capacity - len(self.reserved_patient_ids) - len(self.admitted_patient_ids)


class Ambulance(Contract):
    run_id: ID
    ambulance_id: ID
    display_name: ID
    position: Position
    active_task_id: ID | None


class MedicalTeam(Contract):
    run_id: ID
    team_id: ID
    display_name: ID
    position: Position
    supported_action_types: list[ActionType]
    active_task_id: ID | None

    @model_validator(mode="after")
    def capabilities(self):
        unique(self.supported_action_types, "supported_action_types")
        return self


class DispatchInput(Contract):
    run_id: ID
    patient_id: ID
    position: Position
    current_facility_id: ID | None
    patient_observation: PatientObservation
    treatment_plan: TreatmentPlan
    facilities: list[Facility]
    ambulances: list[Ambulance]
    medical_teams: list[MedicalTeam]

    @model_validator(mode="after")
    def references(self):
        if self.patient_id != self.patient_observation.patient_id or self.patient_id != self.treatment_plan.patient_id:
            raise ValueError("patient identity mismatch")
        for resources, key in ((self.facilities, "facility_id"), (self.ambulances, "ambulance_id"), (self.medical_teams, "team_id")):
            unique([getattr(r, key) for r in resources], key)
            if any(r.run_id != self.run_id for r in resources):
                raise ValueError("cross-run resource reference")
        return self


class DispatchProposal(Contract):
    patient_id: ID
    mode: Mode
    team_id: ID | None
    ambulance_id: ID | None
    target_facility_id: ID | None

    @model_validator(mode="after")
    def mode_references(self):
        actual = (self.team_id is not None, self.ambulance_id is not None, self.target_facility_id is not None)
        expected = {"onsite": (False, False, False), "team_response": (True, False, False), "evacuation": (False, True, True)}
        if actual != expected[self.mode]:
            raise ValueError("resource references do not match dispatch mode")
        return self


class DispatchTask(DispatchProposal):
    task_id: ID
    run_id: ID
    state: TaskState
    accepted_at_s: Time
    treatment_ready_at_s: Time | None
    ended_at_s: Time | None
    detail: str | None

    @model_validator(mode="after")
    def lifecycle(self):
        if (self.state in ENDED) != (self.ended_at_s is not None):
            raise ValueError("ended_at_s must match task state")
        for value in (self.treatment_ready_at_s, self.ended_at_s):
            if value is not None and value < self.accepted_at_s:
                raise ValueError("task time precedes acceptance")
        if self.ended_at_s is not None and self.treatment_ready_at_s is not None and self.treatment_ready_at_s > self.ended_at_s:
            raise ValueError("readiness follows task end")
        if self.state in ("failed", "cancelled"):
            if self.detail is None or not self.detail.strip():
                raise ValueError("failed/cancelled tasks require detail")
        elif self.detail is not None:
            raise ValueError("detail must be null outside failed/cancelled")
        if self.mode == "onsite":
            if self.treatment_ready_at_s != self.accepted_at_s:
                raise ValueError("onsite readiness must equal acceptance")
            if self.state not in ("assigned", "completed", "failed", "cancelled"):
                raise ValueError("onsite has no movement stages")
        if self.mode == "team_response" and self.state in ("transporting", "at_facility"):
            raise ValueError("medical teams do not evacuate patients")
        return self


class TaskEvent(Contract):
    event_id: ID
    run_id: ID
    task_id: ID
    kind: Literal["departed", "arrived_at_patient", "transport_started", "arrived_at_facility"]
    occurred_at_s: Time
    position: Position


class EtaLegRequest(Contract):
    leg: Leg
    resource_id: ID
    origin: Position
    destination: Position
    departure_at_s: Time


class EtaQuery(EtaLegRequest):
    query_id: ID
    run_id: ID
    patient_id: ID


class EtaResult(Contract):
    query_id: ID
    status: Literal["available", "unreachable", "failed"]
    travel_duration_s: Time | None
    detail: str | None

    @model_validator(mode="after")
    def result_fields(self):
        if self.status == "available":
            if self.travel_duration_s is None or self.detail is not None:
                raise ValueError("available ETA requires duration and null detail")
        elif self.travel_duration_s is not None or self.detail is None or not self.detail.strip():
            raise ValueError("unreachable/failed ETA requires null duration and nonblank detail")
        return self


class CallContext(Contract):
    call_id: ID
    run_id: ID
    patient_id: ID


class ErrorInfo(Contract):
    code: Literal["DISPATCH_FAILED", "RESOURCE_UNAVAILABLE", "ETA_FAILED", "ETA_TIMEOUT"]
    message: ID
    request_id: None
    run_id: ID
    patient_id: ID


T = TypeVar("T")


class CallSuccess(Contract, Generic[T]):
    call_id: ID
    data: T


class CallFailure(Contract):
    call_id: ID
    error: ErrorInfo
