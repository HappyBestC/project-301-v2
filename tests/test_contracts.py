import json
from copy import deepcopy
import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML
from core301.paths import FROZEN_ROOT
from core301.contracts.casualty import CasualtyInput, TEMPLATES
from core301.contracts.context import AgentCaseContext, ResourceState
from core301.contracts.observation import PatientObservation, Measurement
from core301.contracts.treatment import TreatmentPlan, ACTION_TYPES, CHEST_ACTIONS
from core301.context.builder import AgentCaseContextBuilder
from core301.fixtures.resource_state import fixed_resources
from core301.pulse.observation_projector import ObservationProjector, BASIC, Sample


def casualty(kind="open_pneumothorax", severity=0.6):
    item = {"injury_type": kind, "severity": severity}
    for key, values in TEMPLATES[kind]["input_enums"].items():
        item[key] = values[0]
    return {"patient_id": "P-001", "injuries": [item]}


def observation():
    return ObservationProjector().project("P-001", 10, {k: Sample(0.5, 10) for k in BASIC})


@pytest.mark.parametrize("kind", TEMPLATES)
@pytest.mark.parametrize("value", [0, 0.2, 0.4, 0.6, 0.8, 1])
def test_injury_all_discrete_values(kind, value):
    assert CasualtyInput.model_validate(casualty(kind, value)).injuries[0].severity == value


@pytest.mark.parametrize("bad", [True, False, "0.4", None, 0.5, 0.55, -1, 2, float("nan"), float("inf")])
def test_invalid_severity(bad):
    with pytest.raises(ValidationError):
        CasualtyInput.model_validate(casualty(severity=bad))


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(extra=1), lambda x: x.update(patient_id="  "),
    lambda x: x.update(patient_id=1), lambda x: x.update(injuries=None),
    lambda x: x["injuries"][0].update(side="Both"),
    lambda x: x["injuries"][0].update(side=None),
    lambda x: x["injuries"][0].pop("side"),
    lambda x: x["injuries"][0].update(compartment=None),
    lambda x: x["injuries"][0].update(injury_type="OpenPneumothorax"),
    lambda x: x["injuries"].append(deepcopy(x["injuries"][0])),
])
def test_invalid_injury_shapes(mutation):
    data = casualty()
    mutation(data)
    with pytest.raises(ValidationError):
        CasualtyInput.model_validate(data)


def test_shared_hemorrhage_identity_and_internal_location():
    a = casualty("external_hemorrhage")
    a["injuries"][0]["compartment"] = "Liver"
    a["injuries"].append({"injury_type": "abdominal_internal_hemorrhage", "severity": 0, "compartment": "Liver"})
    with pytest.raises(ValidationError):
        CasualtyInput.model_validate(a)
    a = casualty("abdominal_internal_hemorrhage")
    a["injuries"][0]["compartment"] = "RightLeg"
    with pytest.raises(ValidationError):
        CasualtyInput.model_validate(a)


def test_six_patterns():
    with (FROZEN_ROOT / "配置/battle_injury_patterns.yaml").open() as stream:
        patterns = YAML(typ="safe").load(stream)["patterns"]
    assert len(patterns) == 6
    for pattern in patterns:
        CasualtyInput(patient_id="P-001", injuries=pattern["injuries"])


@pytest.mark.parametrize("kind", ACTION_TYPES)
def test_all_plan_branches(kind):
    actions = [{"action_type": kind}]
    if kind in CHEST_ACTIONS:
        actions[0]["side"] = "Left"
    if kind == "mechanical_ventilation":
        actions.insert(0, {"action_type": "intubation"})
    TreatmentPlan(patient_id="P-001", actions=actions)


@pytest.mark.parametrize("actions", [
    [{"action_type": "mechanical_ventilation"}],
    [{"action_type": "mechanical_ventilation"}, {"action_type": "intubation"}],
    [{"action_type": "intubation"}, {"action_type": "mechanical_ventilation"}, {"action_type": "supplemental_oxygen"}],
    [{"action_type": "fluid_resuscitation"}, {"action_type": "transfusion"}],
    [{"action_type": "transfusion"}, {"action_type": "fluid_resuscitation"}],
    [{"action_type": "transfusion"}, {"action_type": "transfusion"}],
    [{"action_type": "chest_tube"}],
    [{"action_type": "chest_tube", "side": "Both"}],
    [{"action_type": "transfusion", "side": None}],
    [{"action_type": "transfusion", "rate": 100}],
    [{"action_type": "tourniquet"}],
])
def test_invalid_plans(actions):
    with pytest.raises(ValidationError):
        TreatmentPlan(patient_id="P-001", actions=actions)


@pytest.mark.parametrize("value", [True, "1", 1.0, -1, None])
def test_resource_counts_strict(value):
    data = fixed_resources().model_dump()
    data["medic"] = value
    with pytest.raises(ValidationError):
        ResourceState.model_validate(data)


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf")])
def test_measurement_number_strict(value):
    with pytest.raises(ValidationError):
        Measurement(value=value, status="available", observed_at_s=1)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(laboratory={}), lambda d: d.update(laboratory=None),
    lambda d: d.update(laboratory={"blood_ph": None}),
    lambda d: d.update(severity=0.4), lambda d: d.update(simulation_time_s=True),
    lambda d: d["vitals"]["heart_rate"].update(observed_at_s=11),
    lambda d: d["vitals"]["heart_rate"].update(status="unavailable"),
    lambda d: d["vitals"]["heart_rate"].update(value=None),
    lambda d: d["vitals"]["heart_rate"].update(unit="1/min"),
    lambda d: d["vitals"]["pulse_oximetry"].update(value=98),
    lambda d: d["vitals"].pop("heart_rate"),
])
def test_observation_constraints(mutation):
    data = observation().model_dump(exclude_unset=True)
    mutation(data)
    with pytest.raises(ValidationError):
        PatientObservation.model_validate(data)


def test_context_projection_and_identity():
    context = AgentCaseContextBuilder().build(CasualtyInput.model_validate(casualty(severity=0)), observation(), fixed_resources())
    data = context.model_dump(exclude_unset=True)
    assert "severity" not in json.dumps(data)
    assert data["known_injuries"] == [{"injury_type": "open_pneumothorax", "side": "Left"}]
    AgentCaseContext.model_validate(data)
    for mutation in (
        lambda d: d.update(patient_id="different"),
        lambda d: d["known_injuries"][0].update(severity=0.4),
        lambda d: d["known_injuries"].append(deepcopy(d["known_injuries"][0])),
    ):
        bad = deepcopy(data)
        mutation(bad)
        with pytest.raises(ValidationError):
            AgentCaseContext.model_validate(bad)


def test_default_serialization_omits_absent_groups_but_keeps_measurement_nulls():
    obs = ObservationProjector().project("P-001", 0, {})
    payload = obs.model_dump()
    assert set(payload) == {"patient_id", "simulation_time_s", "vitals"}
    assert payload["vitals"]["heart_rate"] == {"value": None, "status": "unavailable", "observed_at_s": None}
    PatientObservation.model_validate(payload)
    context = AgentCaseContextBuilder().build(CasualtyInput.model_validate(casualty()), obs, fixed_resources())
    AgentCaseContext.model_validate(context.model_dump())
