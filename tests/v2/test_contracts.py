import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core301.contracts.v2.injury import CasualtyInput, INJURY_TYPES, DehydrationCondition
from core301.contracts.v2.treatment import TreatmentPlan, ACTION_TYPES, SIDE_ACTIONS
from core301.pulse.v2.injury_adapter import InjuryAdapter, PatientInitializer
from core301.pulse.v2.protocol_book import validate_injury_scope
from core301.runtime.v2.errors import V2Error


def casualty(kind="external_hemorrhage", severity=0.4):
    injury={"injury_type":kind,"severity":severity}
    if kind in ("external_hemorrhage","abdominal_internal_hemorrhage"):
        injury["compartment"]="RightLeg" if kind=="external_hemorrhage" else "Spleen"
    if kind in ("open_pneumothorax","closed_tension_pneumothorax","hemothorax"):
        injury["side"]="Left"
    return {"patient_id":"P","injuries":[injury]}


def plan(kind="control_external_bleeding"):
    action={"action_type":kind}
    if kind in SIDE_ACTIONS:action["side"]="Left"
    if kind in ("control_external_bleeding","control_internal_bleeding"):
        action["compartment"]="RightLeg" if kind=="control_external_bleeding" else "Spleen"
    sequence=[action]
    if kind=="intubation":sequence.append({"action_type":"mechanical_ventilation"})
    if kind=="mechanical_ventilation":sequence.insert(0,{"action_type":"intubation"})
    return {"patient_id":"P","actions":sequence}


@pytest.mark.parametrize("kind",INJURY_TYPES)
def test_ten_injury_contracts(kind):
    result=CasualtyInput.model_validate(casualty(kind))
    assert result.injuries[0].injury_type==kind
    assert bool(result.conditions)==(kind=="dehydration")
    assert bool(result.dynamic_injuries)==(kind!="dehydration")


@pytest.mark.parametrize("kind",ACTION_TYPES)
def test_twelve_action_contracts(kind):
    assert kind in [x.action_type for x in TreatmentPlan.model_validate(plan(kind)).actions]


@pytest.mark.parametrize("kind",ACTION_TYPES)
@pytest.mark.parametrize("field",["severity","Severity","dose","rate","protocol_id","FlowRate","injury_id","ventilator_parameters"])
def test_forbidden_agent_fields(kind,field):
    payload=plan(kind);payload["actions"][-1][field]=0
    with pytest.raises(ValidationError):TreatmentPlan.model_validate(payload)


@pytest.mark.parametrize("value",["0.4",True,0.3,0.400000000000001,float("nan"),float("inf"),None])
def test_no_severity_rounding_or_type_coercion(value):
    with pytest.raises(ValidationError):CasualtyInput.model_validate(casualty(severity=value))


@pytest.mark.parametrize("kind",["traumatic_brain_injury","airway_obstruction","invented"])
def test_removed_types_only_removed_from_v2(kind):
    with pytest.raises(ValidationError):CasualtyInput.model_validate(casualty(kind))
    from core301.contracts.casualty import TEMPLATES
    assert "traumatic_brain_injury" in TEMPLATES and "airway_obstruction" in TEMPLATES


@pytest.mark.parametrize("mutation",["side","compartment","extra","duplicate","cross_type_collision"])
def test_invalid_injury_location_and_identity(mutation):
    data=casualty()
    if mutation=="side":data=casualty("hemothorax");data["injuries"][0]["side"]="left"
    elif mutation=="compartment":data["injuries"][0]["compartment"]="RightFoot"
    elif mutation=="extra":data["injuries"][0]["FlowRate"]=10
    elif mutation=="duplicate":data["injuries"]*=2
    else:
        data=casualty("abdominal_internal_hemorrhage")
        data["injuries"].append({"injury_type":"external_hemorrhage","compartment":"Spleen","severity":0.4})
    with pytest.raises(ValidationError):CasualtyInput.model_validate(data)


@pytest.mark.parametrize("actions",[
    [{"action_type":"intubation"}], [{"action_type":"mechanical_ventilation"}],
    [{"action_type":"mechanical_ventilation"},{"action_type":"intubation"}],
    [{"action_type":"fluid_resuscitation"},{"action_type":"transfusion"}],
    [{"action_type":"inhaled_albuterol"},{"action_type":"supplemental_oxygen"}],
    [{"action_type":"supplemental_oxygen"},{"action_type":"intubation"},{"action_type":"mechanical_ventilation"}],
    [{"action_type":"transfusion"},{"action_type":"control_external_bleeding","compartment":"RightLeg"}],
    [{"action_type":"chest_tube","side":"Left"},{"action_type":"control_hemothorax_bleeding","side":"Left"}],
    [{"action_type":"chest_tube","side":"Left"}]*2,
    [{"action_type":"needle_decompression","side":"left"}],
    [{"action_type":"control_internal_bleeding","compartment":"RightLeg"}],
    [{"action_type":"control_external_bleeding"}], [{"action_type":"tourniquet"}],
])
def test_conflicts_order_duplicates_unknown(actions):
    with pytest.raises(ValidationError):TreatmentPlan.model_validate({"patient_id":"P","actions":actions})


@pytest.mark.parametrize("kind,level,location",[
    ("external_hemorrhage",0.6,None),("external_hemorrhage",0.4,"LeftArm"),
    ("abdominal_internal_hemorrhage",0.4,"Liver"),("open_pneumothorax",0.6,"Right"),
    ("closed_tension_pneumothorax",0.4,None),("respiratory_muscle_impairment",0.6,None),
    ("impaired_alveolar_exchange",0.8,None),("dehydration",0.8,None),
    ("hemothorax",0.8,None),("bronchoconstriction",0.4,None),("acute_lung_impairment_ards",0.4,None),
])
def test_structurally_valid_but_unopened_scope(kind,level,location):
    data=casualty(kind,level)
    if location:data["injuries"][0]["compartment" if "compartment" in data["injuries"][0] else "side"]=location
    with pytest.raises(V2Error):validate_injury_scope(CasualtyInput.model_validate(data))


@pytest.mark.parametrize("kind",["impaired_alveolar_exchange","dehydration"])
@pytest.mark.parametrize("level",[0.2,0.4,0.6])
def test_exact_open_discrete_points(kind,level):
    assert validate_injury_scope(CasualtyInput.model_validate(casualty(kind,level))).severity==level


def test_condition_has_initialization_only_path():
    data=CasualtyInput.model_validate(casualty("dehydration"))
    assert isinstance(data.injuries[0],DehydrationCondition)
    with pytest.raises(V2Error,match="cannot be submitted"):InjuryAdapter().convert_dynamic(data.injuries[0])
    config=PatientInitializer().configuration(data)
    assert config["Conditions"]["AnyCondition"][0]["PatientCondition"]["Dehydration"]["Severity"]["Scalar0To1"]["Value"]==0.4
    mixed=data.model_dump();mixed["injuries"].append(casualty()["injuries"][0])
    with pytest.raises(V2Error):PatientInitializer().configuration(mixed)


def test_matches_design_examples_with_documented_stricter_order():
    root=Path(__file__).resolve().parents[2]/"research_artifacts/v2_treatment_contract_design/validation/schema_cases.json"
    cases=json.loads(root.read_text())
    for case in cases:
        expected=case["expected_schema_valid"] and case["id"]!="valid_shape_bad_order"
        try:TreatmentPlan.model_validate(case["plan"]);valid=True
        except ValidationError:valid=False
        assert valid==expected,case["id"]
