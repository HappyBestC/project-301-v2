from core301.contracts.casualty import TEMPLATES
from core301.contracts.v2.injury import CasualtyInput, DehydrationCondition
from core301.paths import PULSE_ROOT
from core301.pulse.injury_adapter import scalar
from core301.runtime.v2.errors import V2Error


class InjuryAdapter:
    def convert_dynamic(self, injury):
        if isinstance(injury, DehydrationCondition) or injury.injury_type == "dehydration":
            raise V2Error("CONDITION_REQUIRES_INITIALIZATION", "Dehydration cannot be submitted as an Injury Action")
        if injury.injury_type == "impaired_alveolar_exchange":
            return {"PatientAction": {"ImpairedAlveolarExchangeExacerbation": {"Severity": scalar("0To1", injury.severity)}}}
        template = TEMPLATES[injury.injury_type]
        body = dict(template["fixed"])
        for field in template["input_enums"]:
            body[field.capitalize()] = getattr(injury, field)
        value = scalar("0To1", injury.severity)
        body["Severity"] = ([{"Compartment": lung, "Severity": value} for lung in template["lung_compartments"]]
                            if "lung_compartments" in template else value)
        return {"PatientAction": {template["pulse_action"]: body}}


class PatientInitializer:
    def configuration(self, casualty):
        casualty = CasualtyInput.model_validate(casualty)
        if len(casualty.conditions) != 1 or casualty.dynamic_injuries:
            raise V2Error("INITIALIZATION_SCOPE", "Only the verified single Dehydration Condition configuration is supported")
        condition = casualty.conditions[0]
        if condition.severity not in (0.2, 0.4, 0.6):
            raise V2Error("UNVALIDATED_SCOPE", "Dehydration initialization severity is not verified")
        return {"DataRoot": str(PULSE_ROOT), "PatientFile": str(PULSE_ROOT / "patients/StandardMale.json"),
                "Conditions": {"AnyCondition": [{"PatientCondition": {"Dehydration": {"Severity": scalar("0To1", condition.severity)}}}]}}
