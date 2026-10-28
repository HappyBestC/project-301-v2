from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from ruamel.yaml import YAML
from core301.paths import PROJECT_ROOT
from core301.pulse.observation_projector import BASIC, REQUESTS


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MetricConfig(ConfigModel):
    acceptable_range: tuple[float, float] | None
    weight: float = Field(gt=0)
    distance_tolerance: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered_range(self):
        if self.acceptable_range is not None and self.acceptable_range[0] >= self.acceptable_range[1]:
            raise ValueError("acceptable range must have positive width")
        return self


class EvaluationConfig(ConfigModel):
    calibration_status: Literal["project-configurable", "test-only", "project-approved"]
    evaluation_horizons_s: list[float]
    stable_window_s: float = Field(gt=0)
    max_episode_time_s: float = Field(gt=0)
    max_stability_gap_s: float = Field(gt=0)
    neutral_tolerance: float = Field(ge=0)
    terminal_time_tolerance_s: float = Field(ge=0)
    minimum_scored_metrics: int = Field(ge=1)
    metrics: dict[str, MetricConfig]
    stable_ranges: dict[str, tuple[float, float] | None]
    terminal_event_policy: dict[str, Literal["terminal", "critical"]]

    @model_validator(mode="after")
    def validate_config(self):
        h = self.evaluation_horizons_s
        if not h or any(x <= 0 for x in h) or h != sorted(set(h)):
            raise ValueError("evaluation horizons must be positive, unique and increasing")
        if not set(self.metrics) <= set(REQUESTS):
            raise ValueError("metrics must be Frozen observation paths")
        if not set(BASIC) <= set(self.stable_ranges) <= set(REQUESTS):
            raise ValueError("stable ranges must include all five core vitals")
        if any(r is not None and r[0] >= r[1] for r in self.stable_ranges.values()):
            raise ValueError("stable ranges must have positive width")
        if self.terminal_event_policy.get("IrreversibleState") != "terminal":
            raise ValueError("IrreversibleState must remain terminal")
        from pulse.cdm.bind.Events_pb2 import eEvent
        if not set(self.terminal_event_policy) <= set(eEvent.keys()):
            raise ValueError("unknown Pulse event in terminal policy")
        return self


def load_config(path: Path | str = PROJECT_ROOT / "config/treatment_evaluation.yaml"):
    with Path(path).open(encoding="utf-8") as stream:
        return EvaluationConfig.model_validate(YAML(typ="safe").load(stream))
