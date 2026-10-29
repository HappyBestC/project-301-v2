"""Only JSON data crosses graph node boundaries; providers stay outside state."""
from typing import TypedDict


class ChainState(TypedDict, total=False):
    run_id: str
    run_dir: str
    mode: str
    scenario: str
    horizon_min: float
    cases: list
    triage: dict
    resources: dict
    mapping: dict
    treatment_decisions: dict[str, dict]
    excluded_patients: dict[str, dict]
    dispatch_input: dict
    schedule_attempts: list
    feedback: dict | None
    previous_response: str | None
    accepted_schedule: dict | None
    validation: dict
    timeline: list
    execution: dict[str, dict]
    outcomes: dict
    status: str
    treatment_stage: str
    schedule_stage: str
    schedule_error: dict
    error: dict
