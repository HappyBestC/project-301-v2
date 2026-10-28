"""Event admission awaits the referenced API04 table; no implicit movement policy."""
from dataclasses import dataclass
from typing import Protocol
from .models import DispatchTask, TaskEvent, Position, TaskState, ENDED
from .validation import DispatchError


@dataclass(frozen=True)
class EventTransition:
    state: TaskState
    treatment_ready: bool = False


class TaskEventPolicy(Protocol):
    def __call__(self, task: DispatchTask, event: TaskEvent,
                 patient_position: Position, facility_position: Position | None) -> EventTransition:
        """Verify the confirmed API04 sequence and scene position tolerance; return next stage."""
        ...


def validate_task_event(task, event, *, now_s, last_event_at_s, policy, patient_position, facility_position):
    if (event.run_id, event.task_id) != (task.run_id, task.task_id):
        raise DispatchError("DISPATCH_FAILED", "event task/run identity mismatch")
    if task.state in ENDED or task.mode == "onsite":
        raise DispatchError("DISPATCH_FAILED", "task does not accept movement events")
    if task.mode == "team_response" and event.kind not in ("departed", "arrived_at_patient"):
        raise DispatchError("DISPATCH_FAILED", "medical team cannot report evacuation events")
    if not max(task.accepted_at_s, last_event_at_s) <= event.occurred_at_s <= now_s:
        raise DispatchError("DISPATCH_FAILED", "event simulation time is out of order or in the future")
    if policy is None:
        raise DispatchError("DISPATCH_FAILED", "API04 event admission / position policy is not configured")
    transition = policy(task, event, patient_position, facility_position)
    if transition.state not in ("to_patient", "at_patient", "transporting", "at_facility"):
        raise DispatchError("DISPATCH_FAILED", "Unity movement events cannot end a task")
    # Readiness is a backend precondition, never a Pulse acceptance/success flag.
    return transition
