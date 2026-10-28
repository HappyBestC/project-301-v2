"""Versioned read-only engineering observations, never an efficacy admission."""
from typing import Literal
from pydantic import Field, model_validator
from core301.contracts.base import Contract, PatientId, Time, Number
from core301.contracts.observation import Measurement
from .context import AgentCaseContext

class NativeDrainageEvent(Contract):
    event_type: Literal['native_tube_auto_stop'] = 'native_tube_auto_stop'
    native_time_s: Time
    raw_log_line: str
    source: Literal['Pulse4.3.2.native_log'] = 'Pulse4.3.2.native_log'

class HemothoraxObservation(Contract):
    version: Literal['301.v2.hemothorax.observation.1'] = '301.v2.hemothorax.observation.1'
    patient_id: PatientId
    side: Literal['Left']
    simulation_time_s: Time
    session_epoch: str = Field(min_length=1)
    residual_blood_volume_mL: Measurement
    source_flow_mL_s: Measurement
    source_action_active: bool
    tube_action_active: bool
    tube_flow_mL_min: Number | None
    events: list[NativeDrainageEvent]
    provenance: Literal['Pulse4.3.2.ActionDataRequest+ActiveActions+native_log'] = 'Pulse4.3.2.ActionDataRequest+ActiveActions+native_log'
    numeric_interpretation: Literal['native_raw','negative_native_raw','unavailable']
    clinical_efficacy: Literal['NOT_EVALUATED'] = 'NOT_EVALUATED'
    admission: Literal['PENDING_RESEARCH_RULE_APPROVAL'] = 'PENDING_RESEARCH_RULE_APPROVAL'

    @model_validator(mode='after')
    def coherent(self):
        for m in (self.residual_blood_volume_mL,self.source_flow_mL_s):
            if m.observed_at_s is not None and m.observed_at_s!=self.simulation_time_s:
                raise ValueError('Drainage observations must be current')
        value=self.residual_blood_volume_mL.value
        expected='unavailable' if value is None else 'negative_native_raw' if value<0 else 'native_raw'
        if self.numeric_interpretation!=expected:
            raise ValueError('Raw value must determine numeric classification without correction')
        if any(e.native_time_s>self.simulation_time_s for e in self.events):
            raise ValueError('Native event cannot be in the future')
        if self.tube_flow_mL_min is not None and self.tube_flow_mL_min<0:
            raise ValueError('Negative tube flow is not supported')
        return self

class HemothoraxCaseContext(AgentCaseContext):
    drainage_observation: HemothoraxObservation | None = None

    @model_validator(mode='after')
    def drainage_identity(self):
        d=self.drainage_observation
        if d is not None and (d.patient_id!=self.patient_id or d.simulation_time_s!=self.patient_observation.simulation_time_s):
            raise ValueError('Drainage patient/time mismatch')
        return self
