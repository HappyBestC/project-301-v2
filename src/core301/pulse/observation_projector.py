from dataclasses import dataclass
import math
from core301.contracts.observation import PatientObservation

# Only the Frozen v1 public measurements may be requested or projected.
REQUESTS = {
    "vitals.heart_rate": ("Physiology", "HeartRate", "1/min", None, None),
    "vitals.respiration_rate": ("Physiology", "RespirationRate", "1/min", None, None),
    "vitals.pulse_oximetry": ("Physiology", "PulseOximetry", None, None, None),
    "vitals.systolic_arterial_pressure": ("Physiology", "SystolicArterialPressure", "mmHg", None, None),
    "vitals.mean_arterial_pressure": ("Physiology", "MeanArterialPressure", "mmHg", None, None),
    "circulation.cardiac_output": ("Physiology", "CardiacOutput", "L/min", None, None),
    "respiratory.tidal_volume": ("Physiology", "TidalVolume", "mL", None, None),
    "respiratory.inspired_oxygen_fraction": ("Physiology", "FractionOfInspiredOxygen", None, None, None),
    "laboratory.hemoglobin_concentration": ("Substance", "BloodConcentration", "g/dL", None, "Hemoglobin"),
    "laboratory.lactate_concentration": ("Substance", "BloodConcentration", "mg/dL", None, "Lactate"),
    "laboratory.arterial_oxygen_pressure": ("LiquidCompartment", "PartialPressure", "mmHg", "Aorta", "Oxygen"),
    "laboratory.arterial_carbon_dioxide_pressure": ("LiquidCompartment", "PartialPressure", "mmHg", "Aorta", "CarbonDioxide"),
    "laboratory.blood_ph": ("Physiology", "BloodPH", None, None, None),
    "neurologic.intracranial_pressure": ("Physiology", "IntracranialPressure", "mmHg", None, None),
}
BASIC = tuple(k for k in REQUESTS if k.startswith("vitals."))


@dataclass(frozen=True)
class ObservationAccess:
    """Explicit scenario grants; never inferred from injuries or treatment resources."""
    authorized: frozenset[str] = frozenset()
    relevant: frozenset[str] = frozenset()
    results_obtained: frozenset[str] = frozenset()
    disclose_unavailable: frozenset[str] = frozenset()

    def __post_init__(self):
        allowed = set(REQUESTS) - set(BASIC)
        for values in (self.authorized, self.relevant, self.results_obtained, self.disclose_unavailable):
            if not isinstance(values, frozenset) or not values <= allowed:
                raise ValueError("observation grants must contain only conditional Frozen fields")

    def visible(self):
        return self.authorized & self.relevant & (self.results_obtained | self.disclose_unavailable)


@dataclass(frozen=True)
class Sample:
    value: float | None
    observed_at_s: float | None


class ObservationBuildError(ValueError):
    pass


class ObservationProjector:
    def project(self, patient_id, simulation_time_s, raw: dict[str, Sample], access=None):
        access = access or ObservationAccess()
        result = {"patient_id": patient_id, "simulation_time_s": simulation_time_s}
        for path in (*BASIC, *sorted(access.visible())):
            sample = raw.get(path, Sample(None, None))
            value = sample.value
            valid = type(value) in (int, float) and math.isfinite(value)
            if path not in BASIC:
                valid = valid and path in access.results_obtained
                if not valid and path not in access.disclose_unavailable:
                    continue
            group, field = path.split(".")
            result.setdefault(group, {})[field] = {
                "value": value if valid else None,
                "status": "available" if valid else "unavailable",
                "observed_at_s": sample.observed_at_s,
            }
        try:
            return PatientObservation.model_validate(result)
        except ValueError as exc:
            raise ObservationBuildError(str(exc)) from exc
