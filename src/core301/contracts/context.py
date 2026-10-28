from typing import Annotated
from pydantic import Field, model_validator
from .base import Contract, PatientId
from .casualty import KnownInjury, reject_duplicates
from .observation import PatientObservation

Count = Annotated[int, Field(ge=0)]


class ResourceState(Contract):
    medic: Count
    surgery_team: Count
    airway_kit: Count
    iv_fluid_bag: Count
    chest_tube_kit: Count
    blood_unit: Count
    ventilator: Count
    ambulance: Count


class AgentCaseContext(Contract):
    patient_id: PatientId
    known_injuries: list[KnownInjury]
    patient_observation: PatientObservation
    available_resources: ResourceState

    @model_validator(mode="after")
    def consistent(self):
        reject_duplicates(self.known_injuries)
        if self.patient_id != self.patient_observation.patient_id:
            raise ValueError("patient identity mismatch")
        return self
