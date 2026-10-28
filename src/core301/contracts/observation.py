from typing import Literal
from pydantic import Field, model_validator
from .base import Contract, Number, Time, PatientId


class Measurement(Contract):
    value: Number | None
    status: Literal["available", "unavailable"]
    observed_at_s: Time | None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "available" and (self.value is None or self.observed_at_s is None):
            raise ValueError("available requires value and sample time")
        if self.status == "unavailable" and self.value is not None:
            raise ValueError("unavailable requires null value")
        return self


class Vitals(Contract):
    heart_rate: Measurement
    respiration_rate: Measurement
    pulse_oximetry: Measurement
    systolic_arterial_pressure: Measurement
    mean_arterial_pressure: Measurement


class OptionalGroup(Contract):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError("conditional groups must be nonempty; omit absent fields")
        return self


class Circulation(OptionalGroup):
    cardiac_output: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)


class Respiratory(OptionalGroup):
    tidal_volume: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)
    inspired_oxygen_fraction: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)


class Laboratory(OptionalGroup):
    hemoglobin_concentration: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)
    lactate_concentration: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)
    arterial_oxygen_pressure: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)
    arterial_carbon_dioxide_pressure: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)
    blood_ph: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)


class Neurologic(OptionalGroup):
    intracranial_pressure: Measurement | None = Field(default=None, exclude_if=lambda value: value is None)


class PatientObservation(Contract):
    patient_id: PatientId
    simulation_time_s: Time
    vitals: Vitals
    circulation: Circulation | None = Field(default=None, exclude_if=lambda value: value is None)
    respiratory: Respiratory | None = Field(default=None, exclude_if=lambda value: value is None)
    laboratory: Laboratory | None = Field(default=None, exclude_if=lambda value: value is None)
    neurologic: Neurologic | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def measurements(self):
        for group in ("vitals", "circulation", "respiratory", "laboratory", "neurologic"):
            obj = getattr(self, group)
            if obj is None:
                if group in self.model_fields_set:
                    raise ValueError("omit absent groups instead of null")
                continue
            for key in type(obj).model_fields:
                sample = getattr(obj, key)
                if sample is None:
                    continue
                if sample.observed_at_s is not None and sample.observed_at_s > self.simulation_time_s:
                    raise ValueError("sample time is in the future")
                if key in ("pulse_oximetry", "inspired_oxygen_fraction") and sample.value is not None:
                    if not 0 <= sample.value <= 1:
                        raise ValueError("oxygen fractions must be within [0, 1]")
        return self
