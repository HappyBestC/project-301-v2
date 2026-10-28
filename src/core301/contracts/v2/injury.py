"""Ten draft injury definitions; execution scope lives in the V2 protocol gate."""
from functools import reduce
from operator import or_
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, create_model, model_validator

from core301.contracts.base import Contract, Number, PatientId
from core301.contracts.casualty import TEMPLATES

INJURY_TYPES = (
    "external_hemorrhage", "abdominal_internal_hemorrhage", "open_pneumothorax",
    "closed_tension_pneumothorax", "hemothorax", "bronchoconstriction",
    "acute_lung_impairment_ards", "respiratory_muscle_impairment",
    "impaired_alveolar_exchange", "dehydration",
)
SEVERITIES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def discrete_severity(value):
    if value not in SEVERITIES:
        raise ValueError("V2 severity must be an exact discrete value; no rounding")
    return value


Severity = Annotated[Number, AfterValidator(discrete_severity), Field(json_schema_extra={"enum": list(SEVERITIES)})]


class DehydrationCondition(Contract):
    injury_type: Literal["dehydration"]
    severity: Severity


def injury_union(known=False):
    branches = []
    for name in INJURY_TYPES:
        if name == "dehydration" and not known:
            branches.append(DehydrationCondition)
            continue
        fields = {"injury_type": (Literal[name], ...)}
        if not known:
            fields["severity"] = (Severity, ...)
        for key, values in TEMPLATES.get(name, {}).get("input_enums", {}).items():
            fields[key] = (Literal[tuple(values)], ...)
        branches.append(create_model(("V2Known_" if known else "V2Injury_") + name,
                                     __base__=Contract, **fields))
    return Annotated[reduce(or_, branches), Field(discriminator="injury_type")]


InjuryInput = injury_union()
KnownInjury = injury_union(known=True)


def native_identity(injury):
    name = injury.injury_type
    if name == "dehydration":
        return ("Condition", "Dehydration")
    if name == "impaired_alveolar_exchange":
        return ("ImpairedAlveolarExchangeExacerbation",)
    template = TEMPLATES[name]
    values = {**injury.model_dump(), **template["fixed"]}
    return (template["pulse_action"], *(values[k] for k in template["identity_fields"]))


class CasualtyInput(Contract):
    patient_id: PatientId
    injuries: list[InjuryInput]

    @model_validator(mode="after")
    def identities(self):
        keys = [native_identity(i) for i in self.injuries]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate or colliding native injury identity (Hemorrhage uses compartment only)")
        return self

    @property
    def conditions(self):
        return [i for i in self.injuries if isinstance(i, DehydrationCondition)]

    @property
    def dynamic_injuries(self):
        return [i for i in self.injuries if not isinstance(i, DehydrationCondition)]
