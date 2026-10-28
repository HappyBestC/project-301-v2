from functools import reduce
from operator import or_
from typing import Annotated, Literal
from pydantic import Field, create_model, model_validator
from .base import Contract, PatientId

CHEST_ACTIONS = ("occlusive_dressing", "needle_decompression", "chest_tube")
ACTION_TYPES = (*CHEST_ACTIONS, "fluid_resuscitation", "transfusion", "supplemental_oxygen",
                "intubation", "mechanical_ventilation")
_branches = []
for name in ACTION_TYPES:
    fields = {"action_type": (Literal[name], ...)}
    if name in CHEST_ACTIONS:
        fields["side"] = (Literal["Left", "Right"], ...)
    _branches.append(create_model("Treatment_" + name, __base__=Contract, **fields))
TreatmentAction = Annotated[reduce(or_, _branches), Field(discriminator="action_type")]


class TreatmentPlan(Contract):
    patient_id: PatientId
    actions: list[TreatmentAction]

    @model_validator(mode="after")
    def constraints(self):
        kinds = [a.action_type for a in self.actions]
        keys = [(a.action_type, getattr(a, "side", None)) for a in self.actions]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate treatment identity")
        for first, second in (("fluid_resuscitation", "transfusion"),
                              ("supplemental_oxygen", "mechanical_ventilation")):
            if first in kinds and second in kinds:
                raise ValueError(f"conflicting actions: {first}, {second}")
        if "mechanical_ventilation" in kinds:
            if "intubation" not in kinds or kinds.index("intubation") > kinds.index("mechanical_ventilation"):
                raise ValueError("intubation must precede mechanical ventilation in this plan")
        return self
