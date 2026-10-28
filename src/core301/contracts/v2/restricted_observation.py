"""Versioned observation envelope. Raw specialty observations remain unmodified."""
from typing import Literal
from pydantic import model_validator
from core301.contracts.base import Contract, PatientId, Time
from core301.contracts.observation import PatientObservation, Measurement
from core301.contracts.v2.exposure_validation import ExposureObservation
from core301.contracts.v2.hemothorax_observation import HemothoraxObservation

class RestrictedObservation(Contract):
    version: Literal['301.v2.restricted.observation.1'] = '301.v2.restricted.observation.1'
    injury_type: Literal['hemothorax', 'carbon_monoxide_exposure', 'environmental_hypoxia']
    patient_id: PatientId
    session_epoch: str
    patient_observation: PatientObservation
    specialty: ExposureObservation | HemothoraxObservation
    aorta_sodium_mEq_L: Measurement
    native_events: dict[str, Time]
    production_enabled: Literal[False] = False
    clinical_efficacy: Literal['NOT_EVALUATED'] = 'NOT_EVALUATED'

    @model_validator(mode='after')
    def coherent(self):
        p,s=self.patient_observation,self.specialty
        if p.patient_id!=self.patient_id or s.patient_id!=self.patient_id or s.session_epoch!=self.session_epoch or s.simulation_time_s!=p.simulation_time_s:
            raise ValueError('Observation identity/time mismatch')
        if (self.injury_type=='hemothorax') != isinstance(s,HemothoraxObservation):
            raise ValueError('Wrong specialty observation')
        m=self.aorta_sodium_mEq_L
        if m.observed_at_s!=p.simulation_time_s or m.value is not None and m.value<0:
            raise ValueError('Invalid sodium measurement/time')
        if isinstance(s,ExposureObservation) and m!=s.aorta_sodium_mEq_L:
            raise ValueError('Inconsistent sodium observation')
        if isinstance(s,ExposureObservation) and s.native_events!=self.native_events:
            raise ValueError('Inconsistent native events')
        return self
