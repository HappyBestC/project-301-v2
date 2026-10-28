"""Backend-only identities. Hidden severity is never part of the Agent projection."""
import hashlib
import json
from dataclasses import dataclass, replace
from uuid import uuid4

from core301.contracts.v2.injury import CasualtyInput, native_identity
from .errors import V2Error


@dataclass(frozen=True)
class InjurySource:
    patient_id: str
    injury_id: str
    injury_type: str
    native_key: tuple
    initial_severity: float
    current_severity: float
    source_version: int
    compartment: str | None = None
    side: str | None = None
    authorized: bool = True
    active: bool = True
    controlled: bool = False

    def known(self):
        return {"injury_type": self.injury_type, **({"compartment": self.compartment} if self.compartment else {}),
                **({"side": self.side} if self.side else {})}

    def target(self):
        return {"patient_id": self.patient_id, "injury_id": self.injury_id, "injury_type": self.injury_type,
                "native_identity": list(self.native_key), "source_version": self.source_version,
                **({"compartment": self.compartment} if self.compartment else {}), **({"side": self.side} if self.side else {})}


class InjuryRegistry:
    def __init__(self, patient_id):
        self.patient_id = patient_id
        self._sources = {}

    def register(self, casualty):
        casualty = CasualtyInput.model_validate(casualty)
        if casualty.patient_id != self.patient_id:
            raise V2Error("PATIENT_MISMATCH", "Registry patient mismatch")
        if self._sources:
            raise V2Error("REGISTRY_ALREADY_INITIALIZED", "A new injury episode requires a new runtime")
        for injury in casualty.injuries:
            key = native_identity(injury)
            if key in self._sources:
                raise V2Error("TARGET_AMBIGUOUS", "Native identity collision")
            self._sources[key] = InjurySource(self.patient_id, uuid4().hex, injury.injury_type, key,
                injury.severity, injury.severity, 1, getattr(injury, "compartment", None), getattr(injury, "side", None))

    def sources(self):
        return tuple(self._sources.values())

    def signature(self):
        # Control status may change without creating a new injury episode/version.
        data = [(s.patient_id,s.injury_id,s.injury_type,s.native_key,s.initial_severity,s.source_version,s.authorized,s.active) for s in self.sources()]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def known(self):
        return [s.known() for s in self.sources() if s.authorized and s.active]

    def resolve(self, injury_type, location, patient_id, expected_signature):
        if patient_id != self.patient_id:
            raise V2Error("PATIENT_MISMATCH", "Proxy cannot target another patient")
        if expected_signature != self.signature():
            raise V2Error("STALE_SOURCE", "Registry source version or authorization changed")
        if not self._sources:
            raise V2Error("TARGET_NOT_FOUND", "No injury source is registered")
        if len(self._sources) != 1:
            raise V2Error("UNVALIDATED_MULTISOURCE", "Phase 1 does not control multiple sources")
        matches = [s for s in self.sources() if s.injury_type == injury_type and
                   (s.compartment or s.side) == location and s.authorized and s.active]
        if len(matches) != 1:
            raise V2Error("TARGET_NOT_AUTHORIZED" if not matches else "TARGET_AMBIGUOUS", "Proxy requires exactly one authorized live source")
        return matches[0]

    def mark_controlled(self, injury_id, version):
        for key, source in self._sources.items():
            if source.injury_id == injury_id:
                if source.source_version != version or not source.active:
                    raise V2Error("STALE_SOURCE", "Source changed during execution")
                self._sources[key] = replace(source, current_severity=0.0, controlled=True)
                return
        raise V2Error("TARGET_NOT_FOUND", "Source no longer exists")

    def invalidate(self, injury_id):
        """Trusted backend revocation; never exposed as an Agent action."""
        for key, source in self._sources.items():
            if source.injury_id == injury_id:
                self._sources[key] = replace(source, source_version=source.source_version + 1, active=False)
                return
        raise V2Error("TARGET_NOT_FOUND", "Unknown source")
