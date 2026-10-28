from contextlib import ExitStack
from dataclasses import dataclass
import math

from core301.contracts.treatment import TreatmentPlan
from core301.pulse.observation_projector import ObservationProjector, ObservationAccess
from core301.pulse.state_manager import PulseStateManager
from core301.pulse.treatment_adapter import TreatmentAdapter
from .config import EvaluationConfig, load_config
from .episode_stop import EpisodeStopEvaluator, StopHistory, TIME_EPS
from .models import BranchResult, BranchOrigin, HorizonResult, TreatmentEvaluation
from .treatment_effect import TreatmentEffectEvaluator


@dataclass
class _Branch:
    session: object
    observation: object
    history: StopHistory
    decision: object
    steps: int = 0
    observation_source: str = "current"


class CounterfactualTreatmentEvaluator:
    def __init__(self, config=None, *, access=None, state_manager=None):
        self.config = config or load_config()
        self.access = access or ObservationAccess()
        self.state_manager = state_manager or PulseStateManager()
        self.projector = ObservationProjector()
        self.adapter = TreatmentAdapter()

    def _observe(self, session):
        return self.projector.project(session.patient_id, session.get_simulation_time(),
                                      session.read_requested_data(), self.access)

    def evaluate(self, pulse_session, treatment_plan, evaluation_horizons_s=None, *, episode_start_time_s=0.0):
        plan = TreatmentPlan.model_validate(treatment_plan)
        if plan.patient_id != pulse_session.patient_id:
            raise ValueError("treatment patient identity mismatch")
        config_data = self.config.model_dump()
        if evaluation_horizons_s is not None:
            config_data["evaluation_horizons_s"] = list(evaluation_horizons_s)
        config = EvaluationConfig.model_validate(config_data)
        stop = EpisodeStopEvaluator(config)
        scorer = TreatmentEffectEvaluator(config)
        with ExitStack() as stack:
            snapshot = stack.enter_context(self.state_manager.save_state(pulse_session))
            t0, dt = snapshot.simulation_time_s, snapshot.timestep_s
            if not math.isfinite(episode_start_time_s) or not 0 <= episode_start_time_s <= t0:
                raise ValueError("episode start must lie between zero and decision time")
            if dt > config.max_stability_gap_s + TIME_EPS:
                raise ValueError("native timestep exceeds maximum stability observation gap")
            targets = [round(h / dt) for h in config.evaluation_horizons_s]
            if any(abs(n * dt - h) > TIME_EPS for n, h in zip(targets, config.evaluation_horizons_s)):
                raise ValueError("evaluation horizons must align with the native timestep")
            branches, origins = {}, {}
            for name in ("treatment", "control"):
                session = self.state_manager.fork(snapshot)
                stack.callback(session.close)
                obs = self._observe(session)
                history = StopHistory()
                decision = stop.evaluate(session, obs, history, obs.simulation_time_s - episode_start_time_s)
                branches[name] = _Branch(session, obs, history, decision)
                origins[name] = BranchOrigin(snapshot_sha256=snapshot.sha256, observation=obs)
            if origins["treatment"].observation != origins["control"].observation:
                raise RuntimeError("branches differ at snapshot restoration")
            treatment = branches["treatment"]
            if not treatment.decision.should_stop:
                treatment.session.apply_treatment_actions(self.adapter.convert(plan))
            # Control inherits the snapshot, but receives no new treatment actions.
            results = []
            for horizon, target in zip(config.evaluation_horizons_s, targets):
                outputs = {}
                for name, branch in branches.items():
                    while branch.steps < target and not branch.decision.should_stop:
                        success = branch.session.advance_step()
                        if success:
                            branch.steps += 1
                            branch.observation = self._observe(branch.session)
                        else:
                            # Pulse does not increment time when IrreversibleState aborts a step.
                            # Preserve the previous valid Frozen observation instead of a partial state.
                            branch.observation_source = "last_successful_step"
                        branch.decision = stop.evaluate(branch.session, branch.observation, branch.history,
                                                        branch.observation.simulation_time_s - episode_start_time_s)
                        if not success and branch.decision.episode_state != "terminal":
                            raise RuntimeError("Pulse branch advancement failed without a configured terminal event")
                    decision = branch.decision
                    outputs[name] = BranchResult(
                        observation=branch.observation, episode_state=decision.episode_state,
                        stop_reason=decision.reason, stopped_at_s=decision.triggered_at_s,
                        terminal_time_s=decision.triggered_at_s if decision.episode_state == "terminal" else None,
                        actual_elapsed_s=branch.observation.simulation_time_s - t0,
                        reached_horizon=branch.steps == target,
                        observation_source=branch.observation_source, critical_events=decision.critical_events)
                comparisons, skipped, effect, score, reason = scorer.compare(outputs["treatment"], outputs["control"])
                results.append(HorizonResult(horizon_s=horizon, **outputs, metric_comparisons=comparisons,
                                            skipped_metrics=skipped, effect=effect, score=score, effect_reason=reason))
            return TreatmentEvaluation(
                patient_id=plan.patient_id, decision_time_s=t0, episode_start_time_s=episode_start_time_s,
                treatment_plan=plan, config=config, snapshot_sha256=snapshot.sha256, branch_origins=origins,
                treatment_action_results=branches["treatment"].session.action_results,
                control_action_results=branches["control"].session.action_results,
                branch_results=results, overall_effect=results[-1].effect,
                overall_reason="latest_evaluation_horizon:" + results[-1].effect_reason)
