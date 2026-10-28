from core301.contracts.context import ResourceState


def fixed_resources():
    """Explicit test scenario quantities, never a fallback for unknown live resources."""
    return ResourceState(medic=2, surgery_team=1, airway_kit=1, iv_fluid_bag=2,
                         chest_tube_kit=1, blood_unit=1, ventilator=1, ambulance=1)
