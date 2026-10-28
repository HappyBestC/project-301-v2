from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from core301.contracts.observation import PatientObservation
from core301.contracts.treatment import TreatmentPlan
from .config import EvaluationConfig

Effect = Literal["beneficial", "neutral", "harmful", "unscored"]


class InternalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class StopDecision(InternalModel):
    should_stop: bool
    episode_state: Literal["running", "stable", "terminal", "timeout"]
    reason: str | None = None
    triggered_at_s: float | None = None
    critical_events: list[str] = Field(default_factory=list)


class BranchResult(InternalModel):
    observation: PatientObservation
    episode_state: Literal["running", "stable", "terminal", "timeout"]
    stop_reason: str | None
    stopped_at_s: float | None
    terminal_time_s: float | None
    actual_elapsed_s: float
    reached_horizon: bool
    observation_source: Literal["current", "last_successful_step"] = "current"
    critical_events: list[str] = Field(default_factory=list)


class MetricComparison(InternalModel):
    metric_name: str
    treatment_value: float
    control_value: float
    treatment_distance: float
    control_distance: float
    effect: Literal["improved", "similar", "worse"]
    weighted_score: float


class HorizonResult(InternalModel):
    horizon_s: float
    treatment: BranchResult
    control: BranchResult
    metric_comparisons: list[MetricComparison]
    skipped_metrics: dict[str, str]
    effect: Effect
    score: float | None
    effect_reason: str


class BranchOrigin(InternalModel):
    snapshot_sha256: str
    observation: PatientObservation


class TreatmentEvaluation(InternalModel):
    patient_id: str
    decision_time_s: float
    episode_start_time_s: float
    treatment_plan: TreatmentPlan
    config: EvaluationConfig
    snapshot_sha256: str
    branch_origins: dict[str, BranchOrigin]
    treatment_action_results: list[dict]
    control_action_results: list[dict]
    branch_results: list[HorizonResult]
    overall_effect: Effect
    overall_reason: str
