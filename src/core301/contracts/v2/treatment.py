"""TreatmentPlan V2: twelve strict business actions, no native parameters."""
from functools import reduce
from operator import or_
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, create_model, model_validator

from core301.contracts.base import Contract, PatientId
from core301.contracts.casualty import TEMPLATES

ACTION_TYPES = (
    "control_external_bleeding", "control_internal_bleeding", "control_hemothorax_bleeding",
    "fluid_resuscitation", "transfusion", "occlusive_dressing", "needle_decompression",
    "chest_tube", "inhaled_albuterol", "supplemental_oxygen", "intubation", "mechanical_ventilation",
)
SIDE_ACTIONS = ("control_hemothorax_bleeding", "occlusive_dressing", "needle_decompression", "chest_tube")
LOCATION_INJURY = {"control_external_bleeding": "external_hemorrhage",
                   "control_internal_bleeding": "abdominal_internal_hemorrhage"}
CONFLICTS = (
    ("fluid_resuscitation", "transfusion"), ("supplemental_oxygen", "mechanical_ventilation"),
    ("supplemental_oxygen", "intubation"), ("inhaled_albuterol", "supplemental_oxygen"),
    ("inhaled_albuterol", "intubation"), ("inhaled_albuterol", "mechanical_ventilation"),
)
branches = []
for name in ACTION_TYPES:
    fields = {"action_type": (Literal[name], ...)}
    if name in SIDE_ACTIONS:
        fields["side"] = (Literal["Left", "Right"], ...)
    if name in LOCATION_INJURY:
        fields["compartment"] = (Literal[tuple(TEMPLATES[LOCATION_INJURY[name]]["input_enums"]["compartment"])], ...)
    branches.append(create_model("V2Treatment_" + name, __base__=Contract, **fields))
TreatmentAction = Annotated[reduce(or_, branches), Field(discriminator="action_type")]


def action_identity(action):
    return (action.action_type, getattr(action, "compartment", None), getattr(action, "side", None))


def schema_rules(schema):
    def contains(kind):
        return {"contains":{"type":"object","properties":{"action_type":{"const":kind}},"required":["action_type"]}}
    schema["properties"]["actions"]["uniqueItems"]=True
    # PatientId's inherited AfterValidator is not fully represented by Pydantic's
    # schema generator; export its existing nonblank rule explicitly.
    schema["properties"]["patient_id"].update(minLength=1,pattern=r"\S")
    schema["allOf"]=[{"not":{"properties":{"actions":{"allOf":[contains(first),contains(second)]}}}}
                     for first,second in CONFLICTS]
    for first,second in (("intubation","mechanical_ventilation"),("mechanical_ventilation","intubation")):
        schema["allOf"].append({"if":{"properties":{"actions":contains(first)}},"then":{"properties":{"actions":contains(second)}}})
    schema["description"]="V2 phase-1 contract. JSON structure alone does not grant execution. Array order, target, scope and resource checks also run in the backend."


class TreatmentPlan(Contract):
    model_config=ConfigDict(json_schema_extra=schema_rules)
    patient_id: Annotated[PatientId,Field(min_length=1,pattern=r"\S")]
    actions: list[TreatmentAction]

    @model_validator(mode="after")
    def constraints(self):
        kinds = [a.action_type for a in self.actions]
        keys = [action_identity(a) for a in self.actions]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate treatment identity")
        for first, second in CONFLICTS:
            if first in kinds and second in kinds:
                raise ValueError(f"conflicting actions: {first}, {second}")
        if ("intubation" in kinds) != ("mechanical_ventilation" in kinds):
            raise ValueError("V2 phase 1 requires paired intubation and mechanical ventilation")
        if "intubation" in kinds and kinds.index("intubation") > kinds.index("mechanical_ventilation"):
            raise ValueError("intubation must precede mechanical ventilation")
        for index, action in enumerate(self.actions):
            if action.action_type.startswith("control_"):
                if any(a.action_type in ("fluid_resuscitation", "transfusion") for a in self.actions[:index]):
                    raise ValueError("source control must precede support when both are requested")
                if action.action_type == "control_hemothorax_bleeding" and any(
                    a.action_type == "chest_tube" and a.side == action.side for a in self.actions[:index]
                ):
                    raise ValueError("hemothorax source control must precede same-side drainage")
        return self
