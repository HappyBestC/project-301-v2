import json
from pathlib import Path
import pytest
from core301.contracts.casualty import CasualtyInput, TEMPLATES
from core301.contracts.observation import PatientObservation
from core301.contracts.context import AgentCaseContext
from core301.contracts.treatment import TreatmentPlan, ACTION_TYPES, CHEST_ACTIONS
from core301.pulse.session import PulseSession
from core301.pulse.injury_adapter import InjuryAdapter
from core301.pulse.treatment_adapter import TreatmentAdapter
from core301.pulse.observation_projector import ObservationProjector, REQUESTS, BASIC, ObservationAccess
from core301.runtime.case_runtime import CaseRuntime
from core301.paths import PROJECT_ROOT
from test_contracts import casualty

pytestmark = pytest.mark.integration
FIXTURES = PROJECT_ROOT / "src/core301/fixtures"


@pytest.mark.parametrize("case", json.loads((FIXTURES / "casualties_v1.json").read_text()))
def test_three_casualties(tmp_path, case):
    path = CaseRuntime(case["patient_id"], tmp_path).run_once(case, {"patient_id": case["patient_id"], "actions": []})
    summary = json.loads((path / "run_summary.json").read_text())
    assert summary["status"] == "completed"
    assert all(r["accepted"] for r in summary["injury_apply_result"])
    for file in ("observation_before.json", "observation_after.json"):
        obs = PatientObservation.model_validate_json((path / file).read_text())
        assert all(getattr(obs.vitals, f).status == "available" for f in type(obs.vitals).model_fields)
    AgentCaseContext.model_validate_json((path / "context.json").read_text())
    assert "severity" not in (path / "context.json").read_text()


def test_first_end_to_end_deterministic(tmp_path):
    case = json.loads((FIXTURES / "first_case.json").read_text())
    plan = json.loads((FIXTURES / "first_plan.json").read_text())
    runs = [CaseRuntime(case["patient_id"], tmp_path).run_once(case, plan) for _ in range(2)]
    for name in ("input", "context", "observation_before", "observation_after", "treatment_plan"):
        assert (runs[0] / f"{name}.json").read_text() == (runs[1] / f"{name}.json").read_text()
    summary = json.loads((runs[0] / "run_summary.json").read_text())
    assert summary["treatment_apply_result"][0]["accepted"]
    assert summary["simulation_time_s_after_treatment"] > summary["simulation_time_s_before_observation"] > 0


@pytest.mark.parametrize("kind", TEMPLATES)
def test_all_native_injury_mappings(tmp_path, kind):
    session = PulseSession("P-001")
    try:
        session.initialize(tmp_path / "pulse.log")
        data = casualty(kind, 0.4)
        if "compartment" in data["injuries"][0]:
            data["injuries"][0]["compartment"] = "Spleen" if kind.startswith("abdominal") else "RightLeg"
        session.apply_injury_actions(InjuryAdapter().convert(CasualtyInput.model_validate(data)))
        session.advance_time(1)
        data["injuries"][0]["severity"] = 0
        session.apply_injury_actions(InjuryAdapter().convert(CasualtyInput.model_validate(data)))
        session.advance_time(1)
        assert all(r["accepted"] for r in session.action_results)
    finally:
        session.close()


@pytest.mark.parametrize("kind", ACTION_TYPES)
def test_all_native_treatment_mappings(tmp_path, kind):
    session = PulseSession("P")
    try:
        session.initialize(tmp_path / "pulse.log")
        action = {"action_type": kind}
        if kind in CHEST_ACTIONS:
            action["side"] = "Left"
        actions = ([{"action_type": "intubation"}] if kind == "mechanical_ventilation" else []) + [action]
        session.apply_treatment_actions(TreatmentAdapter().convert(TreatmentPlan(patient_id="P", actions=actions)))
        session.advance_time(1)
        assert all(r["accepted"] for r in session.action_results)
    finally:
        session.close()


def test_all_authorized_observation_sources(tmp_path):
    session = PulseSession("P", requested_fields=tuple(REQUESTS))
    conditional = frozenset(set(REQUESTS) - set(BASIC))
    access = ObservationAccess(conditional, conditional, conditional)
    try:
        session.initialize(tmp_path / "pulse.log")
        session.advance_time(1)
        obs = ObservationProjector().project("P", session.get_simulation_time(), session.read_requested_data(), access)
        payload = obs.model_dump(exclude_unset=True)
        assert sum(len(payload[group]) for group in ("vitals", "circulation", "respiratory", "laboratory", "neurologic")) == 14
        assert all(m["status"] == "available" for group in ("vitals", "circulation", "respiratory", "laboratory", "neurologic") for m in payload[group].values())
    finally:
        session.close()
