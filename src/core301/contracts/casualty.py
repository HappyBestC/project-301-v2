from functools import reduce
from operator import or_
from typing import Annotated, Literal
from pydantic import Field, AfterValidator, create_model, model_validator
from ruamel.yaml import YAML
from core301.paths import FROZEN_ROOT
from .base import Contract, Number, PatientId

with (FROZEN_ROOT / "配置/injury_templates.yaml").open() as stream:
    INJURY_CONFIG = YAML(typ="safe").load(stream)
TEMPLATES = INJURY_CONFIG["templates"]


def severity(value):
    if value not in INJURY_CONFIG["allowed_severities"]:
        raise ValueError("severity must be a Frozen v1 discrete value")
    return value


def injury_union(known=False):
    branches = []
    for name, template in TEMPLATES.items():
        fields = {"injury_type": (Literal[name], ...)}
        if not known:
            fields["severity"] = (Annotated[Number, AfterValidator(severity), Field(json_schema_extra={"enum": INJURY_CONFIG["allowed_severities"]})], ...)
        for key, values in template["input_enums"].items():
            fields[key] = (Literal[tuple(values)], ...)
        branches.append(create_model(("Known_" if known else "Injury_") + name,
                                     __base__=Contract, **fields))
    return Annotated[reduce(or_, branches), Field(discriminator="injury_type")]


InjuryInput = injury_union()
KnownInjury = injury_union(known=True)


def identity(injury):
    template = TEMPLATES[injury.injury_type]
    values = {**injury.model_dump(), **template["fixed"]}
    return (template["pulse_action"], *(values[k] for k in template["identity_fields"]))


def reject_duplicates(injuries):
    keys = [identity(i) for i in injuries]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate native injury identity")


class CasualtyInput(Contract):
    patient_id: PatientId
    injuries: list[InjuryInput]

    @model_validator(mode="after")
    def unique(self):
        reject_duplicates(self.injuries)
        return self
