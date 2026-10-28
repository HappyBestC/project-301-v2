from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Minute = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Count = Annotated[int, Field(ge=0, strict=True)]

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Operation(Model):
    task_id: str
    patient_id: str
    plan_id: str
    action_id: str
    location: str
    start_min: Minute
    end_min: Minute
    staff_ids: list[str]
    equipment_ids: list[str] = []
    space_id: str | None = None
    support_space_id: str | None = None
    access_mode: Literal['new', 'existing'] = 'new'
    access_staff_id: str | None = None
    mode: Literal['start', 'continue'] = 'start'
    continuation_of: str | None = None
    consumables: dict[str, Count]

class Care(Model):
    task_id: str
    operation_id: str
    patient_id: str
    location: str
    start_min: Minute
    end_min: Minute
    staff_id: str

class Transport(Model):
    task_id: str
    patient_id: str
    vehicle_id: str
    departure_location: str
    pickup: str
    destination: str
    start_min: Minute
    load_start_min: Minute
    depart_min: Minute
    arrive_min: Minute
    handoff_end_min: Minute
    end_min: Minute

class PatientResult(Model):
    patient_id: str
    status: Literal['scheduled', 'unscheduled']
    reason_code: Literal['resource_shortage', 'time_window_insufficient', 'missing_parameters', 'no_feasible_schedule_found'] | None = None
    reason: str = ''
    blocking_resources: list[str] = []
    considered_alternatives: list[str] = []

class Schedule(Model):
    version: Literal['301.resource_schedule.v1'] = '301.resource_schedule.v1'
    demonstration_only: bool
    patient_results: list[PatientResult]
    selections: dict[str, str]
    operations: list[Operation]
    transports: list[Transport] = []
    care: list[Care] = []

    @model_validator(mode='after')
    def identities(self):
        ids = [x.task_id for x in self.operations + self.transports + self.care]
        if len(ids) != len(set(ids)):
            raise ValueError('task_id must be unique across operation, transport and care')
        if any(not i.strip() for i in ids):
            raise ValueError('blank task_id')
        for task in self.operations + self.care:
            if task.end_min <= task.start_min:
                raise ValueError('task end must be later than start')
        for task in self.operations:
            if len(task.staff_ids) != len(set(task.staff_ids)) or len(task.equipment_ids) != len(set(task.equipment_ids)):
                raise ValueError('duplicate staff/equipment assignment')
        return self
