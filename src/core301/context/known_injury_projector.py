from pydantic import TypeAdapter
from core301.contracts.casualty import CasualtyInput, KnownInjury, TEMPLATES


def project_known_injuries(casualty):
    """V1 fixture authorizes every input injury, including severity zero entries."""
    casualty = CasualtyInput.model_validate(casualty)
    result = []
    for injury in casualty.injuries:
        item = {"injury_type": injury.injury_type}
        for field in TEMPLATES[injury.injury_type]["input_enums"]:
            item[field] = getattr(injury, field)
        result.append(TypeAdapter(KnownInjury).validate_python(item))
    return result
