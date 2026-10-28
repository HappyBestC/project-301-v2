from core301.contracts.casualty import CasualtyInput, TEMPLATES


def scalar(kind, value, unit=None):
    body = {"Value": value}
    if unit is not None:
        body["Unit"] = unit
    return {"Scalar" + kind: body}


class InjuryAdapter:
    def convert(self, casualty: CasualtyInput) -> list[dict]:
        casualty = CasualtyInput.model_validate(casualty)
        actions = []
        for injury in casualty.injuries:
            template = TEMPLATES[injury.injury_type]
            body = dict(template["fixed"])
            for key in template["input_enums"]:
                body[key.capitalize()] = getattr(injury, key)
            value = scalar("0To1", injury.severity)
            if "lung_compartments" in template:
                body["Severity"] = [{"Compartment": lung, "Severity": value}
                                    for lung in template["lung_compartments"]]
            else:
                body["Severity"] = value
            actions.append({"PatientAction": {template["pulse_action"]: body}})
        return actions
