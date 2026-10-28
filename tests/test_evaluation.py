import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core301.contracts.treatment import TreatmentPlan
from core301.evaluation.config import EvaluationConfig, load_config
from core301.evaluation.counterfactual import CounterfactualTreatmentEvaluator
from core301.evaluation.episode_stop import EpisodeStopEvaluator, StopHistory
from core301.evaluation.models import BranchResult
from core301.evaluation.treatment_effect import TreatmentEffectEvaluator
from core301.pulse.observation_projector import BASIC, ObservationProjector, ObservationAccess, Sample
from core301.pulse import state_manager
from core301.pulse.state_manager import PulseStateManager

CONFIG = Path(__file__).parent / "fixtures/treatment_evaluation.yaml"
NORMAL = [80, 16, 0.98, 120, 90]
PLAN = TreatmentPlan(patient_id="P", actions=[{"action_type": "occlusive_dressing", "side": "Left"}])


@pytest.fixture
def config():
    return load_config(CONFIG)


def configure(config, **updates):
    return EvaluationConfig.model_validate({**config.model_dump(), **updates})


def observe(time=0, hr=80, unavailable=None, *, extra=None, access=None):
    raw = {key: Sample(value, time) for key, value in zip(BASIC, [hr, *NORMAL[1:]])}
    if unavailable is not None:
        raw.pop(unavailable)
    raw.update(extra or {})
    return ObservationProjector().project("P", time, raw, access)


def branch(hr=80, state="running", time=300, reached=True, **kwargs):
    return BranchResult(observation=observe(time, hr), episode_state=state, stop_reason=None,
                        stopped_at_s=time if state != "running" else None,
                        terminal_time_s=time if state == "terminal" else None,
                        actual_elapsed_s=time, reached_horizon=reached, **kwargs)


@pytest.mark.parametrize("t,c,effect,overall", [(110, 140, "improved", "beneficial"),
    (140, 110, "worse", "harmful"), (80, 90, "similar", "neutral"),
    (40, 50, "worse", "harmful"), (100.05, 100, "similar", "neutral")])
def test_range_distance_both_sides_and_tolerance(config, t, c, effect, overall):
    metrics, _, actual, score, _ = TreatmentEffectEvaluator(config).compare(branch(t), branch(c))
    assert metrics[0].effect == effect
    assert metrics[0].treatment_value == t and metrics[0].control_value == c
    assert actual == overall
    assert score is not None


def test_unavailable_is_skipped_not_zero(config):
    t = branch()
    t.observation = observe(300, unavailable=BASIC[0])
    metrics, skipped, *_ = TreatmentEffectEvaluator(config).compare(t, branch())
    assert BASIC[0] in skipped and len(metrics) == 4
    assert all(m.metric_name != BASIC[0] for m in metrics)


def test_no_confirmed_ranges_unscored_and_no_false_stable():
    config = load_config()
    assert TreatmentEffectEvaluator(config).compare(branch(), branch())[2] == "unscored"
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    session = SimpleNamespace(patient_id="P", active_events=lambda: {})
    for time in range(301):
        result = stop.evaluate(session, observe(time), history, time)
    assert result.episode_state == "running" and history.stable_since_s is None


def test_insufficient_available_metrics_unscored(config):
    t = branch()
    t.observation = ObservationProjector().project("P", 300, {})
    assert TreatmentEffectEvaluator(config).compare(t, branch())[2] == "unscored"
    config = configure(config, minimum_scored_metrics=6)
    assert TreatmentEffectEvaluator(config).compare(branch(), branch())[2] == "unscored"


def test_normalized_weights_and_neutral_tolerance(config):
    config = configure(config, neutral_tolerance=0.2)
    # HR improvement 30/40, averaged across five unit-weight metrics = 0.15.
    metrics, _, effect, score, _ = TreatmentEffectEvaluator(config).compare(branch(110), branch(140))
    assert metrics[0].weighted_score == pytest.approx(0.75)
    assert score == pytest.approx(0.15) and effect == "neutral"


def test_conditional_metrics_require_authorized_observation(config):
    path = "neurologic.intracranial_pressure"
    policies = {**config.model_dump()["metrics"], path: {"acceptable_range": [1, 10], "weight": 1, "distance_tolerance": 0}}
    config = configure(config, metrics=policies)
    t, c = branch(), branch()
    grant = frozenset([path])
    access = ObservationAccess(grant, grant, grant)
    t.observation = observe(300, extra={path: Sample(10, 300)}, access=access)
    c.observation = observe(300, extra={path: Sample(20, 300)}, access=access)
    assert TreatmentEffectEvaluator(config).compare(t, c)[0][-1].effect == "improved"
    c.observation = observe(300, extra={path: Sample(20, 300)})
    assert path in TreatmentEffectEvaluator(config).compare(t, c)[1]


@pytest.mark.parametrize("t,c,want", [
    (branch(state="terminal", time=90), branch(), "harmful"),
    (branch(), branch(state="terminal", time=90), "beneficial"),
    (branch(state="terminal", time=110), branch(state="terminal", time=90), "beneficial"),
    (branch(state="terminal", time=80), branch(state="terminal", time=90), "harmful"),
    (branch(state="terminal", time=90), branch(state="terminal", time=90), "neutral"),
    (branch(state="stable", time=60, reached=False), branch(state="terminal", time=90), "unscored"),
])
def test_terminal_outcomes_override_vitals(config, t, c, want):
    metrics, _, effect, score, _ = TreatmentEffectEvaluator(config).compare(t, c)
    assert effect == want and metrics == [] and score is None


def test_early_stable_observations_not_compared_at_future_horizon(config):
    assert TreatmentEffectEvaluator(config).compare(branch(state="stable", time=90, reached=False), branch())[2] == "unscored"


def stop_at(evaluator, history, time, *, hr=80, unavailable=None, events=None):
    session = SimpleNamespace(patient_id="P", active_events=lambda: events or {})
    return evaluator.evaluate(session, observe(time, hr, unavailable), history, time)


def test_stable_requires_full_continuous_window(config):
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    for t in [0, 100, 200, 299]:
        assert not stop_at(stop, history, t).should_stop
    decision = stop_at(stop, history, 300)
    assert decision.should_stop and decision.episode_state == "stable" and decision.triggered_at_s == 300


@pytest.mark.parametrize("disruption", ["bad", "unavailable", "critical"])
def test_stability_timer_resets(config, disruption):
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    for t in [0, 100, 200]:
        stop_at(stop, history, t)
    kwargs = {"bad": {"hr": 150}, "unavailable": {"unavailable": BASIC[0]},
              "critical": {"events": {"CardiacArrest": 0}}}[disruption]
    assert not stop_at(stop, history, 250, **kwargs).should_stop
    assert history.stable_since_s is None
    for t in [300, 400, 500, 599]:
        assert not stop_at(stop, history, t).should_stop
    assert stop_at(stop, history, 600).episode_state == "stable"


def test_sparse_or_stale_data_does_not_prove_continuity(config):
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    stop_at(stop, history, 0)
    assert not stop_at(stop, history, 300).should_stop
    assert history.stable_since_s == 300
    obs = observe(301)
    obs.vitals.heart_rate.observed_at_s = 0
    stop.evaluate(SimpleNamespace(patient_id="P", active_events=lambda: {}), obs, history, 301)
    assert history.stable_since_s is None


def test_timeout_and_stop_is_latched(config):
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    decision = stop_at(stop, history, 3600, hr=150)
    assert decision.episode_state == "timeout" and decision.reason == "max_horizon"
    assert stop_at(stop, history, 3601) == decision


def test_terminal_then_stable_then_timeout_priority(config):
    config = configure(config, max_episode_time_s=300)
    stop, h1, h2 = EpisodeStopEvaluator(config), StopHistory(), StopHistory()
    for t in [0, 100, 200]:
        stop_at(stop, h1, t)
        stop_at(stop, h2, t)
    decision = stop_at(stop, h1, 300, events={"IrreversibleState": 10, "CardiacArrest": 20})
    assert decision.episode_state == "terminal" and decision.triggered_at_s == 290
    assert decision.critical_events == ["CardiacArrest"]
    assert stop_at(stop, h2, 300).episode_state == "stable"


@pytest.mark.parametrize("event", ["CardiacArrest", "CardiovascularCollapse", "CriticalBrainOxygenDeficit", "HypovolemicShock"])
def test_critical_events_are_not_death(config, event):
    decision = stop_at(EpisodeStopEvaluator(config), StopHistory(), 0, events={event: 0})
    assert decision.episode_state == "running" and decision.critical_events == [event]


@pytest.mark.parametrize("change", [
    {"evaluation_horizons_s": [120, 60]}, {"evaluation_horizons_s": []},
    {"evaluation_horizons_s": [60, 60]}, {"evaluation_horizons_s": [float("nan")]},
    {"stable_ranges": {}}, {"stable_window_s": 0}, {"max_episode_time_s": -1},
    {"terminal_event_policy": {"IrreversibleState": "terminal", "ImaginedDeath": "terminal"}},
])
def test_invalid_configuration_rejected(config, change):
    with pytest.raises(ValidationError):
        configure(config, **change)


class FakeSession:
    """Small deterministic simulator double; serializes data, never copies a native object."""
    def __init__(self, patient_id="P", data_root=Path("/tmp"), requested_fields=BASIC):
        self.patient_id, self.data_root, self.requested_fields = patient_id, data_root, requested_fields
        self.time, self.dt, self._spare_time = 60.0, 1.0, 0.0
        self.action_results, self.native_actions = [], []
        self.events = {}
        self.closed = False
        self.terminal_at = None
        self.fail_at = None
        self.fail_terminal = False
        self.advance_calls = 0

    def serialize_state(self):
        return json.dumps({"time": self.time, "native_actions": self.native_actions, "events": self.events})

    def initialize_from_state(self, payload, *, spare_time_s=0):
        data = json.loads(payload)
        self.time, self.native_actions, self.events = data["time"], data["native_actions"], data["events"]
        self._spare_time = spare_time_s

    def get_simulation_time(self): return self.time
    def get_timestep(self): return self.dt
    def active_events(self): return self.events

    def read_requested_data(self):
        hr = 80 if self.native_actions else 140
        return {k: Sample(v, self.time) for k, v in zip(BASIC, [hr, *NORMAL[1:]])}

    def apply_treatment_actions(self, actions):
        self.native_actions.extend(actions)
        self.action_results.extend({"accepted": True, "action": a} for a in actions)

    def advance_step(self):
        self.advance_calls += 1
        if self.fail_at is not None and self.time >= self.fail_at:
            if self.fail_terminal:
                self.events["IrreversibleState"] = 0
            return False
        self.time += self.dt
        if self.terminal_at is not None and self.time >= self.terminal_at:
            self.events["IrreversibleState"] = 0
        return True

    def close(self): self.closed = True


@pytest.fixture
def forks(monkeypatch):
    created = []
    def factory(*args):
        branch = FakeSession(*args)
        created.append(branch)
        return branch
    monkeypatch.setattr(state_manager, "PulseSession", factory)
    return created


def test_same_snapshot_independent_branches_and_cleanup(forks):
    live, manager = FakeSession(), PulseStateManager()
    live._spare_time = 0.5
    original = live.serialize_state()
    with manager.save_state(live) as snapshot:
        t, c = manager.fork(snapshot), manager.fork(snapshot)
        try:
            assert t is not c and t is not live
            assert t.time == c.time == live.time == 60
            assert t._spare_time == c._spare_time == 0.5
            t.apply_treatment_actions([{"test": True}])
            t.advance_step()
            assert c.serialize_state() == original == live.serialize_state()
        finally:
            t.close()
            c.close()
    assert snapshot._state is None
    assert all(b.closed for b in forks) and not live.closed
    with pytest.raises(RuntimeError, match="closed"):
        manager.fork(snapshot)


def test_restore_failure_closes_engine(forks, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError("restore failed")
    monkeypatch.setattr(FakeSession, "initialize_from_state", fail)
    with PulseStateManager().save_state(FakeSession()) as snapshot:
        with pytest.raises(RuntimeError, match="restore failed"):
            PulseStateManager().fork(snapshot)
    assert forks[0].closed


def test_cumulative_horizons_adapter_projector_and_live_isolation(config, forks, monkeypatch):
    live = FakeSession()
    original = live.serialize_state()
    calls = []
    original_project = ObservationProjector.project
    def project(self, *args, **kwargs):
        calls.append(args[1])
        return original_project(self, *args, **kwargs)
    monkeypatch.setattr(ObservationProjector, "project", project)
    result = CounterfactualTreatmentEvaluator(config).evaluate(live, PLAN)
    assert [r.treatment.observation.simulation_time_s for r in result.branch_results] == [120, 180, 360]
    assert [r.control.observation.simulation_time_s for r in result.branch_results] == [120, 180, 360]
    assert result.branch_results[0].treatment.episode_state == "running"
    assert result.branch_results[0].control.episode_state == "running"
    assert result.branch_origins["treatment"] == result.branch_origins["control"]
    assert len(calls) == 602 and result.overall_effect == "beneficial"
    assert forks[0].native_actions == [{"PatientAction": {"ChestOcclusiveDressing": {"Side": "Left", "State": "On"}}}]
    assert result.treatment_action_results and result.control_action_results == []
    assert forks[1].native_actions == []
    assert live.serialize_state() == original and not live.closed
    assert all(b.closed for b in forks)


@pytest.mark.parametrize("terminal_branch,expected", [(0, "harmful"), (1, "beneficial")])
def test_asymmetric_terminal_keeps_true_times_and_stops_advancing(config, forks, monkeypatch, terminal_branch, expected):
    original = FakeSession.initialize_from_state
    def load(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if forks.index(self) == terminal_branch:
            self.terminal_at = 150
    monkeypatch.setattr(FakeSession, "initialize_from_state", load)
    result = CounterfactualTreatmentEvaluator(config).evaluate(FakeSession(), PLAN)
    end = result.branch_results[-1]
    terminal = end.treatment if terminal_branch == 0 else end.control
    survivor = end.control if terminal_branch == 0 else end.treatment
    assert terminal.terminal_time_s == 150 and terminal.actual_elapsed_s == 90
    assert terminal.observation.simulation_time_s == 150 and not terminal.reached_horizon
    assert survivor.observation.simulation_time_s == 360
    assert forks[terminal_branch].advance_calls == 90
    assert end.effect == expected and result.overall_effect == expected


@pytest.mark.parametrize("is_terminal", [False, True])
def test_failed_native_step_needs_terminal_evidence_and_cleans_up(config, forks, monkeypatch, is_terminal):
    original = FakeSession.initialize_from_state
    def load(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if len(forks) == 1:
            self.fail_at, self.fail_terminal = 150, is_terminal
    monkeypatch.setattr(FakeSession, "initialize_from_state", load)
    evaluator = CounterfactualTreatmentEvaluator(config)
    if is_terminal:
        result = evaluator.evaluate(FakeSession(), PLAN)
        item = result.branch_results[-1].treatment
        assert item.terminal_time_s == 150 and item.observation_source == "last_successful_step"
        assert item.observation.simulation_time_s == 150
    else:
        with pytest.raises(RuntimeError, match="without a configured terminal"):
            evaluator.evaluate(FakeSession(), PLAN)
    assert len(forks) == 2 and all(s.closed for s in forks)


def test_second_branch_load_failure_cleans_first_and_snapshot(config, forks, monkeypatch):
    manager = PulseStateManager()
    save = manager.save_state
    captured = []
    def capture(session):
        snapshot = save(session)
        captured.append(snapshot)
        return snapshot
    monkeypatch.setattr(manager, "save_state", capture)
    original = FakeSession.initialize_from_state
    def load(self, *args, **kwargs):
        if len(forks) == 2:
            raise RuntimeError("second fork failed")
        original(self, *args, **kwargs)
    monkeypatch.setattr(FakeSession, "initialize_from_state", load)
    with pytest.raises(RuntimeError, match="second fork"):
        CounterfactualTreatmentEvaluator(config, state_manager=manager).evaluate(FakeSession(), PLAN)
    assert all(s.closed for s in forks) and captured[0]._state is None


def test_timeout_uses_episode_origin_not_decision_time(config, forks):
    config = configure(config, max_episode_time_s=100)
    result = CounterfactualTreatmentEvaluator(config).evaluate(FakeSession(), PLAN)
    assert all(r.treatment.episode_state == r.control.episode_state == "timeout" for r in result.branch_results)
    assert result.branch_results[0].treatment.actual_elapsed_s == 40
    assert result.overall_effect == "unscored"


def test_non_grid_horizon_and_patient_mismatch_rejected(config, forks):
    evaluator = CounterfactualTreatmentEvaluator(config)
    with pytest.raises(ValueError, match="timestep"):
        evaluator.evaluate(FakeSession(), PLAN, [0.5])
    with pytest.raises(ValueError, match="identity"):
        evaluator.evaluate(FakeSession("other"), PLAN)
    assert forks == []


def test_other_patient_and_stale_observation_are_not_compared(config):
    t, c = branch(), branch()
    t.observation.vitals.heart_rate.observed_at_s = 0
    metrics, skipped, *_ = TreatmentEffectEvaluator(config).compare(t, c)
    assert len(metrics) == 4 and skipped[BASIC[0]] == "stale_measurement"
    c.observation.patient_id = "other"
    with pytest.raises(ValueError, match="identity"):
        TreatmentEffectEvaluator(config).compare(t, c)


def test_history_rejects_time_reversal_and_episode_origin_change(config):
    stop, history = EpisodeStopEvaluator(config), StopHistory()
    stop_at(stop, history, 100)
    with pytest.raises(ValueError, match="chronological"):
        stop_at(stop, history, 99)
    with pytest.raises(ValueError, match="origin"):
        stop.evaluate(SimpleNamespace(patient_id="P", active_events=lambda: {}), observe(101), history, 1)


def test_treatment_rejection_cleans_both_branches(config, forks, monkeypatch):
    def reject(*args): raise RuntimeError("action rejected")
    monkeypatch.setattr(FakeSession, "apply_treatment_actions", reject)
    live = FakeSession()
    before = live.serialize_state()
    with pytest.raises(RuntimeError, match="action rejected"):
        CounterfactualTreatmentEvaluator(config).evaluate(live, PLAN)
    assert len(forks) == 2 and all(s.closed for s in forks)
    assert live.serialize_state() == before and not live.closed


def test_snapshot_integrity_failure_creates_no_branch(forks):
    manager = PulseStateManager()
    with manager.save_state(FakeSession()) as snapshot:
        snapshot._state += " "
        with pytest.raises(ValueError, match="integrity"):
            manager.fork(snapshot)
    assert forks == []


def test_event_protobuf_parser_handles_default_enum_and_failed_step():
    from core301.pulse.session import PulseSession
    # Antidiuresis is enum zero, whose Event field is omitted by protobuf JSON.
    payload = json.dumps({"ActiveEvent": [
        {"Duration": {"ScalarTime": {"Value": 2, "Unit": "s"}}},
        {"Event": "IrreversibleState", "Duration": {"ScalarTime": {"Unit": "s"}}},
    ]})
    session = PulseSession("P")
    session._format = None
    session._engine = SimpleNamespace(pull_active_events=lambda fmt: payload)
    session.ready = False  # Reading terminal evidence must work after advance returned False.
    assert session.active_events() == {"Antidiuresis": 2.0, "IrreversibleState": 0.0}


def test_both_terminal_times_respect_configured_tolerance(config):
    config = configure(config, terminal_time_tolerance_s=5)
    assert TreatmentEffectEvaluator(config).compare(
        branch(state="terminal", time=100), branch(state="terminal", time=103)
    )[2] == "neutral"
