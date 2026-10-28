"""Independent episode policy. Caller owns one history per patient/branch."""
from dataclasses import dataclass
import math

from .models import StopDecision

TIME_EPS = 1e-7  # Numerical time comparison only, not a physiological threshold.


def measurement(observation, path):
    group, field = path.split(".")
    return getattr(getattr(observation, group, None), field, None)


@dataclass
class StopHistory:
    patient_id: str | None = None
    episode_start_s: float | None = None
    last_time_s: float | None = None
    stable_since_s: float | None = None
    decision: StopDecision | None = None


class EpisodeStopEvaluator:
    def __init__(self, config):
        self.config = config

    def evaluate(self, session, observation, history, episode_elapsed_s):
        if session.patient_id != observation.patient_id:
            raise ValueError("stop observation patient identity mismatch")
        if not math.isfinite(episode_elapsed_s) or episode_elapsed_s < 0:
            raise ValueError("episode elapsed time must be finite and nonnegative")
        now = observation.simulation_time_s
        start = now - episode_elapsed_s
        if history.patient_id is not None and history.patient_id != observation.patient_id:
            raise ValueError("stop history belongs to a different patient")
        if history.last_time_s is not None and now < history.last_time_s - TIME_EPS:
            raise ValueError("stop history must be chronological")
        if history.episode_start_s is not None and abs(start - history.episode_start_s) > TIME_EPS:
            raise ValueError("episode origin changed")
        if history.decision is not None and history.decision.should_stop:
            return history.decision
        history.patient_id = observation.patient_id
        history.episode_start_s = start
        events = session.active_events()
        critical = sorted(e for e in events if self.config.terminal_event_policy.get(e) == "critical")
        terminal = sorted(e for e in events if self.config.terminal_event_policy.get(e) == "terminal")
        if terminal:
            # Active-event durations are native seconds since activation, including loaded events.
            triggered = max(0.0, min(now - events[e] for e in terminal))
            decision = StopDecision(should_stop=True, episode_state="terminal",
                                    reason="pulse_event:" + ",".join(terminal),
                                    triggered_at_s=triggered, critical_events=critical)
        else:
            gap = history.last_time_s is not None and now - history.last_time_s > self.config.max_stability_gap_s + TIME_EPS
            in_range = not critical
            for path, bounds in self.config.stable_ranges.items():
                m = measurement(observation, path)
                if (bounds is None or m is None or m.status != "available" or m.value is None
                        or m.observed_at_s is None or abs(m.observed_at_s - now) > TIME_EPS
                        or not bounds[0] <= m.value <= bounds[1]):
                    in_range = False
                    break
            if not in_range:
                history.stable_since_s = None
            elif history.stable_since_s is None or gap:
                history.stable_since_s = now
            if history.stable_since_s is not None and now - history.stable_since_s + TIME_EPS >= self.config.stable_window_s:
                decision = StopDecision(should_stop=True, episode_state="stable", reason="stable_window",
                                        triggered_at_s=now, critical_events=critical)
            elif episode_elapsed_s + TIME_EPS >= self.config.max_episode_time_s:
                decision = StopDecision(should_stop=True, episode_state="timeout", reason="max_horizon",
                                        triggered_at_s=now, critical_events=critical)
            else:
                decision = StopDecision(should_stop=False, episode_state="running", critical_events=critical)
        history.last_time_s = now
        history.decision = decision
        return decision
