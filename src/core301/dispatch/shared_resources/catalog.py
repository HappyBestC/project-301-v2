"""Reuse existing research COSTS and frozen scopes, never define clinical requirements."""
from copy import deepcopy
from dataclasses import dataclass
import json
from core301.paths import PROJECT_ROOT
from core301.runtime.v2_1.resources import COSTS
from core301.contracts.v2.treatment import TreatmentPlan


@dataclass(frozen=True)
class TreatmentRequirement:
    action_type: str
    stock: tuple[tuple[str, int], ...]
    holds: tuple[tuple[str, int], ...]
    permission: str | None
    evidence_refs: tuple[str, ...]
    scope_kind: str = 'research_fixture'

    @property
    def requirement_id(self):
        return '301.resource.m2a.1:' + self.action_type


class Catalog:
    def __init__(self):
        costs = deepcopy(COSTS)
        self.requirements = {
            k: TreatmentRequirement(k, tuple(s.items()), tuple(h.items()), p,
                ('src/core301/runtime/v2_1/resources.py:COSTS',
                 'research_artifacts/resource_model_m1/ACTION_RESOURCE_MAPPING.md'))
            for k, (s, h, p) in costs.items()
        }
        path = PROJECT_ROOT / 'research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json'
        self.singles = {p['injury_type']: p for p in json.loads(path.read_text())['profiles']}
        # Use the existing registry's checksum validation rather than accepting a changed bundle.
        from core301.runtime.v2_1.registry import patterns
        self.composites = {p['pattern_id']: p for p in patterns()}
        self.resources = {}
        for _, (stock, holds, _) in costs.items():
            for name in stock:
                self.resources[name] = ('bag' if name.endswith('_bag') else 'kit', 'consumable')
            for name in holds:
                self.resources[name] = ('person' if name == 'medic' else 'team' if name == 'evacuation_team' else 'device', 'reusable')

    def validate_scope(self, plan):
        """Return explicit engineering errors; this does not authorize a Pulse execution."""
        kinds = [a.action_type for a in plan.actions]
        if any(k not in self.requirements for k in kinds):
            return 'CAPABILITY_UNAVAILABLE', 'Action is not in the twelve admitted research resource mappings'
        if plan.scope_id in self.singles:
            p = self.singles[plan.scope_id]
            if not set(kinds) <= set(p['actions']):
                return 'INCOMPATIBLE_RESOURCE', 'Action is outside this fixed single-injury scope'
            if plan.severity not in p.get('severity_levels', [None]):
                return 'CONSTRAINT_UNKNOWN', 'Severity is outside the fixed research profile'
            expected = p.get('location', {})
        elif plan.scope_id in self.composites:
            p = self.composites[plan.scope_id]
            if kinds != p['treatment_bundles']['A'] + p['treatment_bundles']['B'] or plan.severity is not None:
                return 'DEPENDENCY_UNMET', 'Composite scope requires its exact frozen AB sequence'
            expected = {}  # Exact targets below remain fixed in all five AB profiles.
        else:
            return 'CONSTRAINT_UNKNOWN', 'Unknown execution scope; no clinical or runtime admission is inferred'
        for a in plan.actions:
            side = 'Left' if a.action_type in ('chest_tube', 'needle_decompression', 'occlusive_dressing', 'control_hemothorax_bleeding') else None
            compartment = {'control_external_bleeding': 'RightLeg', 'control_internal_bleeding': 'Spleen'}.get(a.action_type)
            if (a.side, a.compartment) != (side, compartment):
                return 'DEPENDENCY_UNMET', 'Action target must match the frozen side/compartment'
            if side and expected.get('side', side) != side:
                return 'DEPENDENCY_UNMET', 'Source side mismatch'
        # Existing V2 contract supplies conflicts, pairing and order. Exposure has its own contract.
        legacy = [dict(action_type=a.action_type, **({'side': a.side} if a.side else {}),
                       **({'compartment': a.compartment} if a.compartment else {}))
                  for a in plan.actions if a.action_type != 'remove_from_exposure']
        try:
            TreatmentPlan.model_validate({'patient_id': plan.patient_id, 'actions': legacy})
        except ValueError as exc:
            return 'DEPENDENCY_UNMET', str(exc)
        if 'chest_tube' in kinds and ('control_hemothorax_bleeding' not in kinds or
                                      kinds.index('control_hemothorax_bleeding') > kinds.index('chest_tube')):
            return 'DEPENDENCY_UNMET', 'Hemothorax source control must precede drainage'
        return None
