"""A V2 facade: no public V1 apply_treatment_actions bypass on this session."""
import hashlib
import json
import math

from core301.paths import PULSE_ROOT
from core301.pulse.session import PulseSession
from .protocol_book import STATE_SHA256, PATIENT_SHA256
from core301.runtime.v2.errors import V2Error

DIAGNOSTICS = (
    ("diagnostic.BloodVolume", {"Category":"Physiology","PropertyName":"BloodVolume","Unit":"mL"}),
    ("diagnostic.TotalHemorrhageRate", {"Category":"Physiology","PropertyName":"TotalHemorrhageRate","Unit":"mL/s"}),
    ("diagnostic.TotalHemorrhagedVolume", {"Category":"Physiology","PropertyName":"TotalHemorrhagedVolume","Unit":"mL"}),
    ("diagnostic.AbdominalCavityVolume", {"Category":"LiquidCompartment","CompartmentName":"AbdominalCavity","PropertyName":"Volume","Unit":"mL"}),
)


class _NativeSession(PulseSession):
    """Internal V1 low-level reuse; additional requests remain backend-only."""
    def _requests_json(self):
        payload = json.loads(super()._requests_json())
        payload["DataRequest"].extend(request for _,request in DIAGNOSTICS)
        return json.dumps(payload)

    def _read(self):
        self._require_ready()
        values = self._engine.pull_data()
        if len(values) != len(self.requested_fields) + len(DIAGNOSTICS) + 1:
            raise V2Error("NATIVE_DATA_SHAPE", "Unexpected Pulse V2 data request shape")
        if not math.isfinite(float(values[0])) or values[0] < 0:
            raise V2Error("NATIVE_TIME_INVALID", "Invalid simulation time")
        return values


class ResearchPulseSession:
    def __init__(self, patient_id, requested_fields):
        self.patient_id = patient_id
        self._native = _NativeSession(patient_id, requested_fields=requested_fields)
        self._initialized = False

    @property
    def ready(self):
        return self._native.ready

    @property
    def action_results(self):
        return list(self._native.action_results)

    def initialize(self, log_path, configuration=None):
        if self._initialized:
            raise V2Error("ALREADY_INITIALIZED", "Condition/Patient initialization cannot be repeated")
        self._initialized = True
        import PyPulse
        if PyPulse.__version__ != "4.3.2":
            raise V2Error("PULSE_VERSION_MISMATCH", "Only Pulse 4.3.2 is verified")
        for relative, digest in [("states/StandardMale@0s.json",STATE_SHA256),("patients/StandardMale.json",PATIENT_SHA256)]:
            if hashlib.sha256((PULSE_ROOT/relative).read_bytes()).hexdigest() != digest:
                raise V2Error("PATIENT_PROVENANCE_MISMATCH", "StandardMale provenance differs from the verified baseline")
        try:
            if configuration is None:
                self._native.initialize(log_path)
            else:
                from google.protobuf.json_format import ParseDict
                from pulse.cdm.bind.Engine_pb2 import PatientConfigurationData
                ParseDict(configuration, PatientConfigurationData())
                self._native._create_engine(log_path)
                self._native.ready = bool(self._native._engine.initialize_engine(
                    json.dumps(configuration), self._native._requests_json(), self._native._format))
                if not self._native.ready:
                    raise V2Error("INITIALIZATION_FAILED", "Pulse rejected Dehydration PatientConfiguration")
                self._native._dt = self._native._engine.get_timestep("s")
        except Exception as exc:
            self._native.ready = False
            if isinstance(exc,V2Error):raise
            raise V2Error("INITIALIZATION_FAILED", str(exc)) from exc

    def _restore_control(self, state):
        if self._initialized:
            raise V2Error("ALREADY_INITIALIZED", "Cannot restore over a running patient")
        self._initialized = True
        self._native.initialize_from_state(state)

    def _submit(self, payload, phase):
        """Called by the trusted runtime only, never from an Agent/provider API."""
        return self._native._apply([payload], phase)[0]

    def advance_time(self, seconds):
        self._native.advance_time(seconds)

    def get_simulation_time(self):
        return self._native.get_simulation_time()

    def read_requested_data(self):
        return self._native.read_requested_data()

    def diagnostics(self):
        values = self._native._read()
        offset = len(self._native.requested_fields) + 1
        return {key:float(v) if math.isfinite(float(v)) else None for (key,_),v in zip(DIAGNOSTICS,values[offset:])}

    def active_events(self):
        return self._native.active_events()

    def serialize_state(self):
        return self._native.serialize_state()

    def execution_state(self):
        state = json.loads(self.serialize_state())
        actions = {}
        for wrapper in state.get("ActiveActions",{}).get("AnyAction",[]):
            for category in wrapper.values():
                for name, body in category.items():
                    actions.setdefault(name,[]).append(body)
        # Protobuf enum Free/Off may be omitted: these defaults are engine-schema
        # values, not imputed physiological measurements.
        return {"actions":actions,"airway_mode":state.get("AirwayMode","Free"),
                "intubation":state.get("Intubation","Off"),
                "ventilator":state.get("MechanicalVentilator",{}),
                "diagnostics":self.diagnostics()}

    def close(self):
        self._native.close()


def native_scalar(body, property_name):
    scalar = body.get(property_name)
    if not isinstance(scalar,dict):return None
    for value in scalar.values():
        if isinstance(value,dict) and ("Value" in value or "Unit" in value):
            return value.get("Value",0.0)
    return None
