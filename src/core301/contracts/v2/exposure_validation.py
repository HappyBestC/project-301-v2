"""Independent validation contracts; these types never grant research admission."""
from typing import Literal
from pydantic import Field, model_validator
from core301.contracts.base import Contract, PatientId, Time, Number
from core301.contracts.observation import Measurement, PatientObservation

ExposureKind = Literal['carbon_monoxide_exposure', 'environmental_hypoxia']

class ExposureInput(Contract):
    patient_id: PatientId
    exposure_id: str = Field(min_length=1)
    exposure_type: ExposureKind
    profile_version: Literal['301.v2.environment.validation.1'] = '301.v2.environment.validation.1'

class EvacuationPlan(Contract):
    patient_id: PatientId
    exposure_id: str = Field(min_length=1)
    action_type: Literal['remove_from_exposure'] = 'remove_from_exposure'

class EvacuationResources(Contract):
    run_id: str = Field(min_length=1)
    patient_id: PatientId
    evacuation_teams: int = Field(ge=0)
    protected_route_available: bool
    receiving_environment_verified: bool
    permission: Literal['research_environment_removal']

class ExposureObservation(Contract):
    version: Literal['301.v2.environment.observation.1'] = '301.v2.environment.observation.1'
    patient_id: PatientId
    exposure_id: str = Field(min_length=1)
    session_epoch: str = Field(min_length=1)
    simulation_time_s: Time
    aorta_co_saturation: Measurement
    aorta_cohb_g_dL: Measurement
    oxygen_saturation: Measurement
    aorta_sodium_mEq_L: Measurement
    ambient_co_fraction: Measurement
    ambient_oxygen_fraction: Measurement
    native_events: dict[str, Time]
    provenance: Literal['Pulse4.3.2.DataRequest+ActiveEvents'] = 'Pulse4.3.2.DataRequest+ActiveEvents'
    admission: Literal['PENDING_RESEARCH_RULE_APPROVAL'] = 'PENDING_RESEARCH_RULE_APPROVAL'
    clinical_efficacy: Literal['NOT_EVALUATED'] = 'NOT_EVALUATED'

    @model_validator(mode='after')
    def current(self):
        for name in ('aorta_co_saturation','aorta_cohb_g_dL','oxygen_saturation','aorta_sodium_mEq_L','ambient_co_fraction','ambient_oxygen_fraction'):
            m=getattr(self,name)
            if m.observed_at_s is not None and m.observed_at_s != self.simulation_time_s:
                raise ValueError('All exposure samples must have the current native time')
            if m.value is not None and (m.value < 0 or ('fraction' in name or 'saturation' in name) and m.value > 1):
                raise ValueError('Invalid native diagnostic range; no clipping allowed')
        return self

class ExposureContext(Contract):
    context_ref: str = Field(min_length=1)
    patient_id: PatientId
    exposure_id: str = Field(min_length=1)
    exposure_type: ExposureKind
    patient_observation: PatientObservation
    exposure_observation: ExposureObservation | None
    available_evacuation_teams: int = Field(ge=0)
    production_enabled: Literal[False] = False

    @model_validator(mode='after')
    def identity(self):
        if self.patient_observation.patient_id != self.patient_id:
            raise ValueError('Patient identity mismatch')
        d=self.exposure_observation
        if d and (d.patient_id != self.patient_id or d.exposure_id != self.exposure_id or d.simulation_time_s != self.patient_observation.simulation_time_s):
            raise ValueError('Exposure identity/time mismatch')
        return self
