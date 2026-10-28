"""Compare contemporaneous branches, never change relative to a pretreatment baseline."""
from .episode_stop import measurement, TIME_EPS
from .models import MetricComparison


def distance(value, bounds):
    low, high = bounds
    return max(low - value, 0.0, value - high)


class TreatmentEffectEvaluator:
    def __init__(self, config):
        self.config = config

    def compare(self, treatment, control):
        if treatment.observation.patient_id != control.observation.patient_id:
            raise ValueError("branch observation patient identity mismatch")
        comparisons, skipped = [], {}
        terminal_t = treatment.episode_state == "terminal"
        terminal_c = control.episode_state == "terminal"
        if terminal_t or terminal_c:
            if terminal_t and terminal_c:
                delta = treatment.terminal_time_s - control.terminal_time_s
                tolerance = self.config.terminal_time_tolerance_s
                effect = "beneficial" if delta > tolerance + TIME_EPS else "harmful" if delta < -tolerance - TIME_EPS else "neutral"
                reason = "both_terminal_compare_activation_times"
            else:
                survivor, terminal = (control, treatment) if terminal_t else (treatment, control)
                if survivor.observation.simulation_time_s + TIME_EPS < terminal.terminal_time_s:
                    effect, reason = "unscored", "survivor_censored_before_terminal_time"
                else:
                    effect = "harmful" if terminal_t else "beneficial"
                    reason = "terminal_outcome_priority"
            return comparisons, {p: "terminal_outcome_priority" for p in self.config.metrics}, effect, None, reason
        if not treatment.reached_horizon or not control.reached_horizon or abs(
            treatment.observation.simulation_time_s - control.observation.simulation_time_s
        ) > TIME_EPS:
            return [], {p: "noncontemporaneous_observations" for p in self.config.metrics}, "unscored", None, "branch_stopped_before_horizon"
        weight_sum = 0.0
        for path, policy in self.config.metrics.items():
            tm = measurement(treatment.observation, path)
            cm = measurement(control.observation, path)
            if any(m is None or m.status != "available" or m.value is None for m in (tm, cm)):
                skipped[path] = "unavailable_or_undisclosed"
                continue
            if any(m.observed_at_s is None or abs(m.observed_at_s - b.observation.simulation_time_s) > TIME_EPS
                   for m, b in ((tm, treatment), (cm, control))):
                skipped[path] = "stale_measurement"
                continue
            if policy.acceptable_range is None:
                skipped[path] = "acceptable_range_not_configured"
                continue
            dt, dc = (distance(m.value, policy.acceptable_range) for m in (tm, cm))
            delta = dc - dt
            effect = "improved" if delta > policy.distance_tolerance else "worse" if delta < -policy.distance_tolerance else "similar"
            width = policy.acceptable_range[1] - policy.acceptable_range[0]
            score = 0.0 if effect == "similar" else policy.weight * delta / width
            comparisons.append(MetricComparison(metric_name=path, treatment_value=tm.value,
                                                control_value=cm.value, treatment_distance=dt,
                                                control_distance=dc, effect=effect, weighted_score=score))
            weight_sum += policy.weight
        if len(comparisons) < self.config.minimum_scored_metrics:
            return comparisons, skipped, "unscored", None, "insufficient_configured_available_metrics"
        score = sum(m.weighted_score for m in comparisons) / weight_sum
        effect = "beneficial" if score > self.config.neutral_tolerance else "harmful" if score < -self.config.neutral_tolerance else "neutral"
        return comparisons, skipped, effect, score, "weighted_normalized_range_distance"
