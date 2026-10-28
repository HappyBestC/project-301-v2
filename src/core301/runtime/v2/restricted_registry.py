"""Additive research registry; legacy scopes and clinical labels are unchanged."""
from dataclasses import dataclass
from types import MappingProxyType
from core301.pulse.v2.protocol_book import OPEN_INJURIES, ALLOWED_ACTIONS, PROFILE_VERSION

VERSION = '301.v2.restricted.acceptance.1'
@dataclass(frozen=True)
class ResearchProfile:
    injury_type: str
    profile: str
    decision_s: int
    end_s: int
    actions: frozenset[str]
    admission: str
    blocker: str | None = None
    production_enabled: bool = False

REGISTRY = MappingProxyType({
    **{k: ResearchProfile(k, PROFILE_VERSION, 180, 480, ALLOWED_ACTIONS[k], 'ADMITTED_LEGACY') for k in OPEN_INJURIES},
    'hemothorax': ResearchProfile('hemothorax', '301.v2.hemothorax.restricted.1', 660, 960,
        frozenset({'control_hemothorax_bleeding', 'chest_tube'}), 'ADMITTED_RESTRICTED'),
    'carbon_monoxide_exposure': ResearchProfile('carbon_monoxide_exposure', '301.v2.co.removal.restricted.1', 960, 1860,
        frozenset({'remove_from_exposure'}), 'ADMITTED_RESTRICTED'),
    'environmental_hypoxia': ResearchProfile('environmental_hypoxia', '301.v2.hypoxia.removal.restricted.1', 360, 660,
        frozenset({'remove_from_exposure'}), 'ADMITTED_RESTRICTED'),
})
# Engineering authorization: current task C3/C4 and stage 4; final user acceptance
# is deliberately not represented by a forged owner/date/signature here.
