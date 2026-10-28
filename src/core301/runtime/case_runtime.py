import json
from pathlib import Path
from uuid import uuid4
from core301.contracts.casualty import CasualtyInput
from core301.contracts.treatment import TreatmentPlan
from core301.context.builder import AgentCaseContextBuilder
from core301.fixtures.resource_state import fixed_resources
from core301.agent.manual_provider import ManualTreatmentProvider
from core301.pulse.session import PulseSession
from core301.pulse.injury_adapter import InjuryAdapter
from core301.pulse.treatment_adapter import TreatmentAdapter
from core301.pulse.observation_projector import ObservationProjector, ObservationAccess, BASIC
from .capability import ScenarioSupplies, validate_capability


def serialize(value):
    return value.model_dump(exclude_unset=True) if hasattr(value, "model_dump") else value


def write_json(path, value):
    Path(path).write_text(json.dumps(serialize(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


class CaseRuntime:
    """Single patient, single first-decision loop. No replay, resource arbitration or replan."""
    def __init__(self, patient_id, runs_dir="runs", access=None, session=None, supplies=None):
        self.patient_id = patient_id
        self.access = access or ObservationAccess()
        requests = (*BASIC, *sorted(self.access.visible()))
        self.session = session or PulseSession(patient_id, requested_fields=requests)
        if self.session.patient_id != patient_id:
            raise ValueError("session patient identity mismatch")
        self.runs_dir = Path(runs_dir)
        self.supplies = supplies or ScenarioSupplies()
        self.casualty = None
        self._executed = False
        self._ran = False

    def initialize(self):
        self.session.initialize(self.run_dir / "pulse_debug.log" if hasattr(self, "run_dir") else None)

    def apply_casualty(self, casualty):
        casualty = CasualtyInput.model_validate(casualty)
        if casualty.patient_id != self.patient_id:
            raise ValueError("casualty patient identity mismatch")
        if self.casualty is not None:
            raise RuntimeError("V1 runtime accepts one casualty batch per case")
        self.session.apply_injury_actions(InjuryAdapter().convert(casualty))
        self.casualty = casualty

    def observe(self):
        raw = self.session.read_requested_data()
        return ObservationProjector().project(self.patient_id, self.session.get_simulation_time(), raw, self.access)

    def build_context(self, observation=None):
        if self.casualty is None:
            raise RuntimeError("apply casualty before building context")
        return AgentCaseContextBuilder().build(self.casualty, observation or self.observe(), fixed_resources())

    def execute_plan(self, plan, context=None):
        if self._executed:
            raise RuntimeError("V1 runtime does not replay treatment plans")
        plan = TreatmentPlan.model_validate(plan)
        context = context or self.build_context()
        validate_capability(plan, context, self.supplies)
        self._executed = True
        return self.session.apply_treatment_actions(TreatmentAdapter().convert(plan))

    def run_once(self, casualty, plan=None, *, provider=None, before_s=60.0, after_s=60.0):
        if self._ran:
            raise RuntimeError("create a new runtime for each run")
        self._ran = True
        run_id = uuid4().hex
        self.run_dir = self.runs_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        summary = {"run_id": run_id, "patient_id": self.patient_id, "status": "running",
                   "resource_mode": "fixed_test_fixture"}
        phase = "input_validation"
        try:
            casualty = CasualtyInput.model_validate(casualty)
            write_json(self.run_dir / "input.json", casualty)
            if (plan is None) == (provider is None):
                raise ValueError("supply exactly one of plan or provider")
            provider = provider if provider is not None else ManualTreatmentProvider(plan)
            phase = "initialize"
            self.initialize()
            phase = "injury"
            self.apply_casualty(casualty)
            phase = "advance_before"
            self.session.advance_time(before_s)
            phase = "observation_before"
            before = self.observe()
            write_json(self.run_dir / "observation_before.json", before)
            summary["simulation_time_s_before_observation"] = before.simulation_time_s
            phase = "context"
            context = self.build_context(before)
            write_json(self.run_dir / "context.json", context)
            phase = "plan"
            plan = TreatmentPlan.model_validate(provider.create_plan(context))
            write_json(self.run_dir / "treatment_plan.json", plan)
            phase = "treatment"
            self.execute_plan(plan, context)
            phase = "advance_after"
            self.session.advance_time(after_s)
            phase = "observation_after"
            after = self.observe()
            write_json(self.run_dir / "observation_after.json", after)
            summary["simulation_time_s_after_treatment"] = after.simulation_time_s
            summary["status"] = "completed"
            return self.run_dir
        except Exception as exc:
            summary.update(status="failed", failed_phase=phase, error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            for name in ("injury", "treatment"):
                summary[name + "_apply_result"] = [r for r in self.session.action_results if r["phase"] == name]
            write_json(self.run_dir / "run_summary.json", summary)
            self.session.close()
