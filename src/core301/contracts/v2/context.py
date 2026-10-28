from pydantic import model_validator
from core301.contracts.base import Contract, PatientId
from core301.contracts.context import ResourceState
from core301.contracts.observation import PatientObservation
from .injury import KnownInjury, native_identity


class AgentCaseContext(Contract):
    patient_id: PatientId
    known_injuries: list[KnownInjury]
    patient_observation: PatientObservation
    available_resources: ResourceState

    @model_validator(mode="after")
    def consistent(self):
        if self.patient_id != self.patient_observation.patient_id:
            raise ValueError("context patient identity mismatch")
        keys = [native_identity(i) for i in self.known_injuries]
        if len(keys) != len(set(keys)):
            raise ValueError("colliding known injury identity")
        return self
