import pytest
from core301.contracts.casualty import CasualtyInput, TEMPLATES
from core301.contracts.treatment import TreatmentPlan
from core301.pulse.injury_adapter import InjuryAdapter
from core301.pulse.treatment_adapter import TreatmentAdapter
from core301.pulse.observation_projector import ObservationProjector, ObservationAccess, Sample, BASIC
from core301.runtime.capability import ScenarioSupplies, validate_capability
from core301.context.builder import AgentCaseContextBuilder
from core301.fixtures.resource_state import fixed_resources
from test_contracts import casualty, observation


def test_mapping_zero_and_ards():
    expected = {"external_hemorrhage": "Hemorrhage", "abdominal_internal_hemorrhage": "Hemorrhage",
                "open_pneumothorax": "TensionPneumothorax", "closed_tension_pneumothorax": "TensionPneumothorax",
                "hemothorax": "Hemothorax", "traumatic_brain_injury": "BrainInjury",
                "airway_obstruction": "AirwayObstruction", "bronchoconstriction": "Bronchoconstriction",
                "acute_lung_impairment_ards": "AcuteRespiratoryDistressSyndromeExacerbation",
                "respiratory_muscle_impairment": "RespiratoryFatigue"}
    for kind in TEMPLATES:
        native = InjuryAdapter().convert(CasualtyInput.model_validate(casualty(kind, 0)))[0]["PatientAction"]
        assert set(native) == {expected[kind]}
        body = native[expected[kind]]
        if kind == "acute_lung_impairment_ards":
            assert [x["Compartment"] for x in body["Severity"]] == ["LeftLung", "RightLung"]
            assert all(x["Severity"]["Scalar0To1"]["Value"] == 0 for x in body["Severity"])
        else:
            assert body["Severity"]["Scalar0To1"]["Value"] == 0
    assert InjuryAdapter().convert(CasualtyInput(patient_id="P", injuries=[])) == []


def test_treatment_fixed_parameters():
    def native(kind, side=None):
        a = {"action_type": kind}
        if side: a["side"] = side
        actions = ([{"action_type": "intubation"}] if kind == "mechanical_ventilation" else []) + [a]
        result = TreatmentAdapter().convert(TreatmentPlan(patient_id="P", actions=actions))[-1]
        return next(iter(next(iter(result.values())).values()))
    assert native("occlusive_dressing", "Left") == {"Side": "Left", "State": "On"}
    assert native("needle_decompression", "Right") == {"Side": "Right", "State": "On"}
    assert native("chest_tube", "Left")["FlowRate"] == {"ScalarVolumePerTime": {"Value": 30, "Unit": "mL/min"}}
    for kind, compound in (("transfusion", "Blood"), ("fluid_resuscitation", "Saline")):
        body = native(kind)
        assert body["SubstanceCompound"] == compound
        assert body["BagVolume"]["ScalarVolume"] == {"Value": 500, "Unit": "mL"}
        assert body["Rate"]["ScalarVolumePerTime"] == {"Value": 100, "Unit": "mL/min"}
    oxygen = native("supplemental_oxygen")
    assert oxygen == {"Device": "NonRebreatherMask", "Flow": {"ScalarVolumePerTime": {"Value": 15, "Unit": "L/min"}},
                      "Volume": {"ScalarVolume": {"Value": 425, "Unit": "L"}}}
    assert native("intubation") == {"Type": "Tracheal"}
    vent = native("mechanical_ventilation")
    assert vent["MechanicalVentilatorMode"] == {"Connection": "On"}
    assert vent["Mode"] == "AssistedControl"
    for key, scalar, value, unit in (("InspiratoryPressure", "Pressure", 13, "cmH2O"),
                                     ("PositiveEndExpiratoryPressure", "Pressure", 5, "cmH2O"),
                                     ("RespirationRate", "Frequency", 12, "1/min"),
                                     ("InspiratoryPeriod", "Time", 1, "s"), ("Slope", "Time", 0.1, "s")):
        assert vent[key]["Scalar" + scalar] == {"Value": value, "Unit": unit}
    assert vent["FractionInspiredOxygen"]["Scalar0To1"]["Value"] == 0.21


def test_observation_gating_and_failed_reads():
    field = "neurologic.intracranial_pressure"
    raw = {field: Sample(22, 3), "BloodVolume": Sample(5000, 3), BASIC[0]: Sample(0, 3), BASIC[1]: Sample(float("nan"), 3)}
    projector = ObservationProjector()
    base = projector.project("P", 5, raw).model_dump(exclude_unset=True)
    assert set(base) == {"patient_id", "simulation_time_s", "vitals"}
    assert base["vitals"]["heart_rate"]["value"] == 0
    assert base["vitals"]["respiration_rate"] == {"value": None, "status": "unavailable", "observed_at_s": 3}
    assert base["vitals"]["pulse_oximetry"]["observed_at_s"] is None
    grant = frozenset([field])
    for access in (ObservationAccess(authorized=grant), ObservationAccess(authorized=grant, relevant=grant)):
        assert projector.project("P", 5, raw, access).neurologic is None
    access = ObservationAccess(authorized=grant, relevant=grant, results_obtained=grant)
    assert projector.project("P", 5, raw, access).neurologic.intracranial_pressure.observed_at_s == 3
    access = ObservationAccess(authorized=grant, relevant=grant, disclose_unavailable=grant)
    assert projector.project("P", 5, raw, access).neurologic.intracranial_pressure.value is None
    with pytest.raises(ValueError):
        ObservationAccess(authorized=frozenset(["BloodVolume"]))


def test_capability_checks_use_known_side_and_supplies():
    context = AgentCaseContextBuilder().build(CasualtyInput.model_validate(casualty()), observation(), fixed_resources())
    for action in ({"action_type": "occlusive_dressing", "side": "Right"},
                   {"action_type": "chest_tube", "side": "Left"}):
        with pytest.raises(ValueError):
            validate_capability(TreatmentPlan(patient_id="P-001", actions=[action]), context, ScenarioSupplies())
    for kind, supplies in (("supplemental_oxygen", ScenarioSupplies(nrb_mask=False)),
                           ("fluid_resuscitation", ScenarioSupplies(saline_bag_ml=0)),
                           ("transfusion", ScenarioSupplies(blood_bag_ml=0))):
        with pytest.raises(ValueError):
            validate_capability(TreatmentPlan(patient_id="P-001", actions=[{"action_type": kind}]), context, supplies)
