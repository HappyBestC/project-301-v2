from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioSupplies:
    """Explicit simulator fixture capabilities, separate from the eight resource counts."""
    saline_bag_ml: int = 500
    blood_bag_ml: int = 500
    nrb_mask: bool = True
    oxygen_l: int = 425


def validate_capability(plan, context, supplies):
    if plan.patient_id != context.patient_id:
        raise ValueError("treatment patient identity mismatch")
    matching = {"occlusive_dressing": {"open_pneumothorax"},
                "needle_decompression": {"open_pneumothorax", "closed_tension_pneumothorax"},
                "chest_tube": {"hemothorax"}}
    for action in plan.actions:
        if action.action_type in matching and not any(
            injury.injury_type in matching[action.action_type]
            and getattr(injury, "side", None) == action.side for injury in context.known_injuries
        ):
            raise ValueError("chest treatment requires matching authorized injury and side")
        if action.action_type == "supplemental_oxygen" and (not supplies.nrb_mask or supplies.oxygen_l < 425):
            raise ValueError("scenario lacks NRB and 425 L oxygen supply")
        if action.action_type == "fluid_resuscitation" and supplies.saline_bag_ml < 500:
            raise ValueError("scenario lacks 500 mL Saline bag")
        if action.action_type == "transfusion" and supplies.blood_bag_ml < 500:
            raise ValueError("scenario lacks 500 mL Blood bag")
    # V1 uses a fixed resource fixture; live allocation and contention are out of scope.
