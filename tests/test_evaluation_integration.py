"""Actual installed Pulse 4.3.2; no network or model provider."""
import json
from pathlib import Path
from hashlib import sha256

import pytest

from core301.evaluation.config import load_config
from core301.evaluation.counterfactual import CounterfactualTreatmentEvaluator
from core301.evaluation.demo import demo_inputs
from core301.evaluation.models import TreatmentEvaluation
from core301.contracts.treatment import TreatmentPlan
from core301.pulse.injury_adapter import InjuryAdapter
from core301.pulse.observation_projector import ObservationProjector, BASIC, REQUESTS
from core301.pulse.session import PulseSession
from core301.pulse.state_manager import PulseStateManager
from core301.pulse.treatment_adapter import TreatmentAdapter

pytestmark = pytest.mark.integration


class RecordingManager(PulseStateManager):
    def __init__(self):
        self.branches = []
        self.source_hashes = []
        self.snapshot = None

    def save_state(self, session):
        self.snapshot = super().save_state(session)
        return self.snapshot

    def fork(self, snapshot):
        self.source_hashes.append(sha256(snapshot._state.encode()).hexdigest())
        branch = super().fork(snapshot)
        self.branches.append(branch)
        return branch


def test_real_pulse_counterfactual_60_120_300_and_live_unchanged(tmp_path):
    import PyPulse
    assert PyPulse.__version__ == "4.3.2"
    casualty, plan = demo_inputs()
    live = PulseSession(casualty.patient_id)
    manager = RecordingManager()
    try:
        live.initialize(tmp_path / "live.log")
        live.apply_injury_actions(InjuryAdapter().convert(casualty))
        live.advance_time(60)
        original_state = json.loads(live.serialize_state())
        original_data = live.read_requested_data()
        original_actions = [dict(a) for a in live.action_results]
        result = CounterfactualTreatmentEvaluator(
            load_config(Path(__file__).parent / "fixtures/treatment_evaluation.yaml"), state_manager=manager
        ).evaluate(live, plan)
        assert result.decision_time_s == pytest.approx(60)
        assert manager.source_hashes == [result.snapshot_sha256] * 2
        assert manager.branches[0]._engine is not manager.branches[1]._engine
        assert all(b._engine is not live._engine for b in manager.branches)
        assert result.branch_origins["treatment"].observation == result.branch_origins["control"].observation
        assert result.branch_origins["control"].observation.simulation_time_s == pytest.approx(60)
        for horizon in result.branch_results:
            assert horizon.treatment.reached_horizon and horizon.control.reached_horizon
            assert horizon.treatment.observation.simulation_time_s == pytest.approx(60 + horizon.horizon_s)
            assert horizon.control.observation.simulation_time_s == pytest.approx(60 + horizon.horizon_s)
            assert len(horizon.metric_comparisons) == 5
        assert len(result.treatment_action_results) == 2
        assert all(a["accepted"] for a in result.treatment_action_results)
        assert result.control_action_results == []
        assert result.branch_results[-1].treatment.observation != result.branch_results[-1].control.observation
        assert live.get_simulation_time() == pytest.approx(60)
        assert live.read_requested_data() == original_data
        assert live.action_results == original_actions
        assert json.loads(live.serialize_state()) == original_state
        assert all(not b.ready for b in manager.branches)
        assert manager.snapshot._state is None
        # Frozen observations and new internal results both round-trip without schema additions.
        payload = result.model_dump_json()
        assert TreatmentEvaluation.model_validate_json(payload) == result
        (tmp_path / "evaluation.json").write_text(payload)
        print(f"real Pulse {PyPulse.__version__}: t0=60, T/C @120/180/360, effect={result.overall_effect}, live unchanged")
    finally:
        live.close()


def test_real_snapshot_preserves_prior_actions_events_requests_and_independence(tmp_path):
    casualty, plan = demo_inputs()
    live = PulseSession(casualty.patient_id, requested_fields=tuple(REQUESTS))
    manager = PulseStateManager()
    t = c = None
    try:
        live.initialize(tmp_path / "live.log")
        live.apply_injury_actions(InjuryAdapter().convert(casualty))
        live.advance_time(60.01)  # Include the wrapper's fractional-step remainder.
        prior_plan = TreatmentPlan(patient_id=casualty.patient_id, actions=[{"action_type": "supplemental_oxygen"}])
        live.apply_treatment_actions(TreatmentAdapter().convert(prior_plan))
        live.advance_time(1)
        live_state = json.loads(live.serialize_state())
        live_events = live.active_events()
        with manager.save_state(live) as snapshot:
            t, c = manager.fork(snapshot), manager.fork(snapshot)
            assert t._spare_time == c._spare_time == live._spare_time
            assert t.requested_fields == c.requested_fields == tuple(REQUESTS)
            assert t.read_requested_data() == c.read_requested_data() == live.read_requested_data()
            assert t.active_events() == c.active_events() == live_events
            assert json.loads(c.serialize_state())["ActiveActions"] == live_state["ActiveActions"]
            assert "SupplementalOxygen" in json.dumps(live_state["ActiveActions"])
            assert c.action_results == []  # Prior therapy persists, but C submits no new action.
            control_state = json.loads(c.serialize_state())
            t.apply_treatment_actions(TreatmentAdapter().convert(plan))
            t.advance_time(1)
            assert c.get_simulation_time() == live.get_simulation_time()
            assert json.loads(c.serialize_state()) == control_state
            assert json.loads(live.serialize_state()) == live_state
            c.advance_time(1)
            assert t.get_simulation_time() == c.get_simulation_time()
            assert t.read_requested_data() != c.read_requested_data()
        assert snapshot._state is None
        assert {p.name for p in tmp_path.iterdir()} <= {"live.log"}
    finally:
        for session in (t, c, live):
            if session is not None:
                session.close()
