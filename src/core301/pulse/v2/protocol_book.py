"""Immutable phase-1 research profiles. No profile is production enabled."""
from types import MappingProxyType
from core301.runtime.v2.errors import V2Error

PROFILE_VERSION = "301.v2.phase1.research.1"
STATE_SHA256 = "0867d7ed38a62fa8f77e16c85b8f0849401868846b276bdee0041ac58393ca7d"
PATIENT_SHA256 = "df99d070d06ae3b7f81e863e991499eabbe092f7c72c884146f293bf4c87eaa2"
OPEN_INJURIES = MappingProxyType({
    "external_hemorrhage": ((0.4,), "compartment", "RightLeg"),
    "abdominal_internal_hemorrhage": ((0.4,), "compartment", "Spleen"),
    "open_pneumothorax": ((0.6,), "side", "Left"),
    "closed_tension_pneumothorax": ((0.6,), "side", "Left"),
    "respiratory_muscle_impairment": ((0.4,), None, None),
    "impaired_alveolar_exchange": ((0.2, 0.4, 0.6), None, None),
    "dehydration": ((0.2, 0.4, 0.6), None, None),
})
ALLOWED_ACTIONS = MappingProxyType({
    "external_hemorrhage": frozenset(("control_external_bleeding", "fluid_resuscitation", "transfusion")),
    "abdominal_internal_hemorrhage": frozenset(("control_internal_bleeding", "fluid_resuscitation", "transfusion")),
    "open_pneumothorax": frozenset(("occlusive_dressing",)),
    "closed_tension_pneumothorax": frozenset(("needle_decompression",)),
    "respiratory_muscle_impairment": frozenset(("intubation", "mechanical_ventilation")),
    "impaired_alveolar_exchange": frozenset(("supplemental_oxygen",)),
    "dehydration": frozenset(("fluid_resuscitation",)),
})
RESERVED_ACTIONS = frozenset(("control_hemothorax_bleeding", "chest_tube", "inhaled_albuterol"))
# Separate evidence status from permission. Phase-2 mechanism experiments do
# not make these profiles executable through CaseRuntime or TreatmentAdapter.
SPECIALTY_DECISIONS = MappingProxyType({
    "hemothorax": ("BLOCKED", "Native drainage and auto-stop observable; negative residual and authorized drainage endpoint unresolved"),
    "bronchoconstriction": ("PARTIALLY_VALIDATED", "Both fixed forced and spontaneous inhalation candidates trigger delivery; respiratory alkalosis and persistent heart-rate increase require protocol safety review"),
    "acute_lung_impairment_ards": ("REQUIRES_VALIDATION", "NC0.5 and NC1 improve oxygenation but residual hypoxemia and adverse CO2/pH response lack accepted safety disposition"),
})
RESERVED_PROTOCOL_DESCRIPTIONS = MappingProxyType({
    "control_hemothorax_bleeding":"Same-side Severity0 proxy; contract reserved; no phase-1 business execution",
    "chest_tube":"TubeThoracostomy 30mL/min; native drainage/auto-stop observed; authorized drainage endpoint and negative residual disposition unresolved",
    "inhaled_albuterol":"Candidate Albuterol90ug/NozzleLoss.04/Spacer500mL → forced exhale3s/UseInhaler/inspire12s+hold3s+release5s; actual trigger/long device lifecycle confirmed, safety unaccepted",
    "oxygen.ards.nc05":"Candidate NC.5L/min,425L; residual hypoxemia/CO2/pH safety unresolved; not executable",
    "oxygen.legacy.nrb15":"NRB15L/min,425L excluded from V2 release; hyperoxemia/ARDS acidosis counterexamples retained",
})


def validate_injury_scope(casualty):
    if len(casualty.injuries) != 1:
        raise V2Error("UNVALIDATED_COMBINATION", "Phase 1 requires exactly one injury/condition source")
    injury = casualty.injuries[0]
    if injury.injury_type not in OPEN_INJURIES:
        status, reason = SPECIALTY_DECISIONS.get(injury.injury_type, ("BLOCKED", "Unregistered injury profile"))
        raise V2Error("INJURY_NOT_OPEN", status + ": " + reason)
    levels, location, expected = OPEN_INJURIES[injury.injury_type]
    if injury.severity not in levels or (location and getattr(injury, location) != expected):
        raise V2Error("UNVALIDATED_SCOPE", "Injury severity/location is outside the verified phase-1 profile")
    return injury


def protocol_id(injury_type, action_type):
    if action_type not in ALLOWED_ACTIONS.get(injury_type, ()):
        raise V2Error("ACTION_NOT_OPEN", "No approved research protocol for this injury/action")
    return ("oxygen.alveolar.nc05" if action_type == "supplemental_oxygen" else action_type) + ".phase1.1"
