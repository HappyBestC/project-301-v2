import json
import pytest
from core301.pulse.session import PulseSession, ActionApplyError
from core301.pulse.observation_projector import BASIC, Sample
from core301.runtime.case_runtime import CaseRuntime
from core301.agent.manual_provider import ManualTreatmentProvider


class EngineStub:
    def __init__(self, acceptance):
        self.acceptance = iter(acceptance)
        self.calls = []
    def pull_data(self):
        return [0, 80, 16, 0.98, 120, 90]
    def process_actions(self, payload, fmt):
        self.calls.append(json.loads(payload))
        return next(self.acceptance)


def test_native_rejection_stops_dependent_ventilation():
    # Schema parsing uses the actual generated protobuf definitions.
    from core301.pulse.treatment_adapter import TreatmentAdapter
    from core301.contracts.treatment import TreatmentPlan
    session = PulseSession("P")
    session.ready = True
    session._engine = EngineStub([False, True])
    session._format = None
    plan = TreatmentPlan(patient_id="P", actions=[{"action_type": "intubation"}, {"action_type": "mechanical_ventilation"}])
    with pytest.raises(ActionApplyError):
        session.apply_treatment_actions(TreatmentAdapter().convert(plan))
    assert len(session._engine.calls) == 1
    assert session.action_results[0]["accepted"] is False
    assert not session.ready


class SessionStub:
    patient_id = "P"
    def __init__(self):
        self.action_results = []
        self.time = 0
        self.closed = False
    def initialize(self, log_path=None): pass
    def apply_injury_actions(self, actions): pass
    def advance_time(self, seconds): self.time += seconds
    def get_simulation_time(self): return self.time
    def read_requested_data(self): return {k: Sample(0.5, self.time) for k in BASIC}
    def apply_treatment_actions(self, actions):
        self.action_results.append({"phase": "treatment", "index": 0, "accepted": False, "simulation_time_s": self.time})
        raise ActionApplyError("injected native rejection")
    def close(self): self.closed = True


def test_failure_is_persisted_without_post_treatment_observation(tmp_path):
    session = SessionStub()
    runtime = CaseRuntime("P", runs_dir=tmp_path, session=session)
    with pytest.raises(ActionApplyError):
        runtime.run_once({"patient_id": "P", "injuries": []}, {"patient_id": "P", "actions": [{"action_type": "intubation"}]})
    summary = json.loads((runtime.run_dir / "run_summary.json").read_text())
    assert summary["status"] == "failed" and summary["failed_phase"] == "treatment"
    assert summary["treatment_apply_result"][0]["accepted"] is False
    assert not (runtime.run_dir / "observation_after.json").exists()
    assert session.time == 60 and session.closed
    with pytest.raises(RuntimeError):
        runtime.run_once({}, {})


def test_provider_receives_context_only_and_id_mismatch_rejected(tmp_path):
    session = SessionStub()
    runtime = CaseRuntime("P", runs_dir=tmp_path, session=session)
    plan = {"patient_id": "other", "actions": []}
    with pytest.raises(ValueError, match="patient_id"):
        runtime.run_once({"patient_id": "P", "injuries": []}, provider=ManualTreatmentProvider(plan))
    assert json.loads((runtime.run_dir / "run_summary.json").read_text())["failed_phase"] == "plan"
    assert not session.action_results
