import json
import math
from pathlib import Path
from core301.paths import PULSE_ROOT
from .observation_projector import REQUESTS, BASIC, Sample


class ActionApplyError(RuntimeError):
    pass


class PulseSession:
    """One native patient. All native access, including acceptance checks, stays here."""
    def __init__(self, patient_id, data_root=PULSE_ROOT, requested_fields=BASIC):
        self.patient_id = patient_id
        self.data_root = Path(data_root).resolve()
        self.requested_fields = tuple(requested_fields)
        if len(set(self.requested_fields)) != len(self.requested_fields) or not set(self.requested_fields) <= set(REQUESTS):
            raise ValueError("invalid or duplicate DataRequest")
        if not set(BASIC) <= set(self.requested_fields):
            raise ValueError("all five vital requests are required")
        self._engine = None
        self.ready = False
        self.action_results = []
        self._spare_time = 0.0

    def initialize(self, log_path=None):
        self._create_engine(log_path)
        self.ready = self._engine.serialize_from_file(str(self.data_root / "states/StandardMale@0s.json"),
                                                      self._requests_json(), self._format)
        if not self.ready:
            raise RuntimeError("Pulse StandardMale initialization failed")
        self._dt = self._engine.get_timestep("s")

    def _create_engine(self, log_path=None):
        if self._engine is not None:
            raise RuntimeError("session has already been initialized")
        import PyPulse
        self._format = PyPulse.serialization_format.json
        self._engine = PyPulse.Engine(PyPulse.model_type.human_adult_whole_body, str(self.data_root))
        self._engine.log_to_console(False)
        if log_path is not None:
            self._engine.set_log_filename(str(Path(log_path).resolve()))

    def _requests_json(self):
        from google.protobuf.json_format import ParseDict
        from pulse.cdm.bind.Engine_pb2 import DataRequestManagerData
        requests = []
        for field in self.requested_fields:
            category, prop, unit, compartment, substance = REQUESTS[field]
            request = {"Category": category, "PropertyName": prop}
            for name, value in (("Unit", unit), ("CompartmentName", compartment), ("SubstanceName", substance)):
                if value is not None:
                    request[name] = value
            requests.append(request)
        payload = {"DataRequest": requests}
        ParseDict(payload, DataRequestManagerData())
        return json.dumps(payload)

    def serialize_state(self):
        self._require_ready()
        state = self._engine.serialize_to_string(self._format)
        if not state:
            raise RuntimeError("Pulse state serialization failed")
        return state

    def initialize_from_state(self, state, *, spare_time_s=0.0):
        self._create_engine()
        self.ready = self._engine.serialize_from_string(state, self._requests_json(), self._format)
        if not self.ready:
            raise RuntimeError("Pulse state restoration failed")
        self._dt = self._engine.get_timestep("s")
        self._spare_time = spare_time_s

    def get_timestep(self):
        self._require_ready()
        return float(self._dt)

    def advance_step(self):
        """Evaluation-only single step; False needs event inspection, not a death assumption."""
        self._require_ready()
        success = bool(self._engine.advance_timestep())
        if not success:
            self.ready = False
        return success

    def active_events(self):
        """Read even after a failed step. Values are active durations in seconds."""
        if self._engine is None:
            raise RuntimeError("Pulse session has not been initialized")
        from google.protobuf.json_format import Parse
        from pulse.cdm.bind.Events_pb2 import ActiveEventListData, eEvent
        payload = self._engine.pull_active_events(self._format)
        message = Parse(payload, ActiveEventListData()) if payload else ActiveEventListData()
        events = {}
        for event in message.ActiveEvent:
            duration = event.Duration.ScalarTime
            if duration.Unit != "s" or not math.isfinite(duration.Value) or duration.Value < 0:
                raise RuntimeError("invalid native event duration")
            events[eEvent.Name(event.Event)] = float(duration.Value)
        return events

    def _require_ready(self):
        if not self.ready:
            raise RuntimeError("Pulse session is not ready")

    def _apply(self, actions, phase):
        self._require_ready()
        from google.protobuf.json_format import ParseDict
        from pulse.cdm.bind.Engine_pb2 import ActionListData
        records = []
        for index, action in enumerate(actions):
            record = {"phase": phase, "index": index, "simulation_time_s": self.get_simulation_time(),
                      "accepted": False}
            try:
                payload = {"AnyAction": [action]}
                ParseDict(payload, ActionListData())
                if not self._engine.process_actions(json.dumps(payload), self._format):
                    raise ActionApplyError(f"Pulse rejected {phase} action {index}")
                record["accepted"] = True
            except Exception as exc:
                record["error"] = str(exc)
                self.ready = False
                raise ActionApplyError(f"{phase} action {index} failed: {exc}") from exc
            finally:
                self.action_results.append(record)
                records.append(record)
        return records

    def apply_injury_actions(self, actions):
        return self._apply(actions, "injury")

    def apply_treatment_actions(self, actions):
        return self._apply(actions, "treatment")

    def advance_time(self, seconds):
        self._require_ready()
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("duration must be finite nonnegative seconds")
        total = seconds + self._spare_time
        steps = int(total / self._dt)
        for _ in range(steps):
            if not self._engine.advance_timestep():
                self.ready = False
                raise RuntimeError("Pulse time advancement failed")
        self._spare_time = total - steps * self._dt

    def _read(self):
        self._require_ready()
        values = self._engine.pull_data()
        if len(values) != len(self.requested_fields) + 1:
            raise RuntimeError("Pulse returned unexpected DataRequest shape")
        if not math.isfinite(float(values[0])) or values[0] < 0:
            raise RuntimeError("invalid native simulation time")
        return values

    def get_simulation_time(self):
        return float(self._read()[0])

    def read_requested_data(self):
        values = self._read()
        return {key: Sample(float(value), float(values[0]))
                for key, value in zip(self.requested_fields, values[1:])}

    def close(self):
        if self._engine is not None:
            self._engine.clear()
        self.ready = False
