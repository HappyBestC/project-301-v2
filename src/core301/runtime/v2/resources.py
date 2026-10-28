"""Explicit resource authority boundary and a bounded in-memory research fixture.

This is not a production inventory service. Reservation precedes all submissions;
per-step acquisition can still fail if credentials or inventory are revoked.
"""
from collections import Counter
from dataclasses import dataclass
from threading import RLock
from typing import Protocol

from core301.contracts.context import ResourceState
from core301.contracts.treatment import TreatmentPlan as V1Plan
from core301.dispatch.validation import required_action_types
from .errors import V2Error

COSTS = {
    "control_external_bleeding": ({}, {"medic":1}, "simulated_external_source_control"),
    "control_internal_bleeding": ({}, {"medic":1}, "simulated_internal_source_control"),
    "occlusive_dressing": ({"occlusive_dressing_kit":1}, {"medic":1}, None),
    "needle_decompression": ({"needle_kit":1}, {"medic":1}, None),
    "fluid_resuscitation": ({"saline_500ml_bag":1}, {"medic":1}, "iv_access"),
    "transfusion": ({"blood_500ml_bag":1}, {"medic":1}, "iv_access"),
    "intubation": ({"airway_kit":1}, {"medic":1}, None),
    "mechanical_ventilation": ({}, {"ventilator":1}, None),
    "supplemental_oxygen": ({}, {"medic":1,"nasal_cannula":1,"oxygen_425l_source":1}, None),
}


class ResourceAuthority(Protocol):
    authority_kind: str
    def snapshot(self, run_id, patient_id) -> ResourceState: ...
    def reserve(self, plan_id, plan, run_id, patient_id) -> dict: ...
    def begin(self, plan_id, action_id, action_type) -> dict: ...
    def acknowledge(self, plan_id, action_id, accepted: bool | None) -> None: ...
    def release_unused(self, plan_id) -> None: ...
    def audit(self) -> dict: ...
    def close_case(self) -> None: ...


@dataclass
class _Reservation:
    stock: Counter
    holds: dict
    begun: dict


class ResearchResourceFixture:
    authority_kind = "explicit_research_fixture"

    def __init__(self, run_id, patient_id, *, stock, holds, capabilities, permissions):
        self.run_id = run_id
        self.patient_id = patient_id
        for value in [*stock.values(),*holds.values()]:
            if type(value) is not int or value<0:
                raise ValueError("Resource quantities must be explicit nonnegative integers")
        self.stock = Counter(stock)
        self.holds = dict(holds)
        self.capabilities = frozenset(capabilities)
        self.permissions = frozenset(permissions)
        self._reservations = {}
        self._lock = RLock()

    def _identity(self, run_id, patient_id):
        if (run_id,patient_id)!=(self.run_id,self.patient_id):
            raise V2Error("RESOURCE_IDENTITY_MISMATCH", "Resource credential belongs to another run/patient")

    def snapshot(self, run_id, patient_id):
        with self._lock:
            self._identity(run_id,patient_id)
            reserved = sum((r.stock for r in self._reservations.values()),Counter())
            held = Counter()
            for r in self._reservations.values():held.update(r.holds)
            return ResourceState(medic=max(0,self.holds.get("medic",0)-held["medic"]),surgery_team=0,
                airway_kit=max(0,self.stock["airway_kit"]-reserved["airway_kit"]),
                iv_fluid_bag=max(0,self.stock["saline_500ml_bag"]-reserved["saline_500ml_bag"]),
                chest_tube_kit=0,blood_unit=max(0,self.stock["blood_500ml_bag"]-reserved["blood_500ml_bag"]),
                ventilator=max(0,self.holds.get("ventilator",0)-held["ventilator"]),ambulance=0)

    def reserve(self, plan_id, plan, run_id, patient_id):
        with self._lock:
            self._identity(run_id,patient_id)
            if plan_id in self._reservations:
                raise V2Error("RESOURCE_RESERVATION_DUPLICATE", "Reservation cannot be recreated")
            # The V1 helper validates a V1Plan, so reuse it only for the legacy
            # subset. V2 proxy capabilities are explicitly added, not cast to V1.
            legacy=[a.model_dump() for a in plan.actions if not a.action_type.startswith("control_")]
            required=required_action_types(V1Plan(patient_id=patient_id,actions=legacy)) | frozenset(
                a.action_type for a in plan.actions if a.action_type.startswith("control_"))
            if not required<=self.capabilities:
                raise V2Error("CAPABILITY_UNAVAILABLE", "Whole plan capability credential is missing")
            demand=Counter();holds={}
            for action in plan.actions:
                stock,needed,permission=COSTS[action.action_type]
                if permission and permission not in self.permissions:
                    raise V2Error("PROCEDURE_NOT_AUTHORIZED", "Backend procedure/IV permission is missing")
                demand.update(stock)
                for key,count in needed.items():holds[key]=max(holds.get(key,0),count)
            reserved=sum((r.stock for r in self._reservations.values()),Counter())
            used_holds=Counter()
            for r in self._reservations.values():used_holds.update(r.holds)
            if any(self.stock[k]-reserved[k]<n for k,n in demand.items()) or any(self.holds.get(k,0)-used_holds[k]<n for k,n in holds.items()):
                raise V2Error("RESOURCE_UNAVAILABLE", "Explicit fixture lacks required stock/equipment/personnel")
            self._reservations[plan_id]=_Reservation(demand,holds,{})
            return {"authority_kind":self.authority_kind,"reserved_units":dict(demand),"held_units":holds.copy(),"production_inventory":False}

    def begin(self, plan_id, action_id, action_type):
        with self._lock:
            r=self._reservations[plan_id]
            if action_id in r.begun:
                raise V2Error("RESOURCE_REPLAY_BLOCKED", "Cannot acquire the same action twice")
            stock,_,permission=COSTS[action_type]
            if action_type not in self.capabilities or (permission and permission not in self.permissions):
                raise V2Error("RESOURCE_REVOKED", "Capability/procedure revoked after reservation")
            if any(self.stock[k]<n or r.stock[k]<n for k,n in stock.items()):
                raise V2Error("RESOURCE_UNAVAILABLE", "Reserved resource changed before this action")
            for key,count in stock.items():
                self.stock[key]-=count;r.stock[key]-=count
            r.begun[action_id]={"allocated_units":dict(stock),"submission_status":"pending","delivery_status":"not_confirmed"}
            return r.begun[action_id].copy()

    def acknowledge(self, plan_id, action_id, accepted):
        with self._lock:
            r=self._reservations[plan_id]
            r.begun[action_id]["submission_status"]="accepted" if accepted is True else "quarantined"
            # A bag is allocated once. This is not a claim all its fluid was given.
            r.begun[action_id]["delivery_status"]="pending_advance" if accepted is True else "unknown"

    def release_unused(self, plan_id):
        with self._lock:
            r=self._reservations.get(plan_id)
            if r is not None:r.stock.clear()
            # Keep committed kits and persistent device/personnel holds conservative.

    def close_case(self):
        with self._lock:
            self._reservations.clear()

    def audit(self):
        return {"authority_kind":self.authority_kind,"stock_units_remaining":dict(self.stock),
                "reservations":{k:{"stock":dict(r.stock),"holds":r.holds,"begun":r.begun} for k,r in self._reservations.items()},
                "limitation":"In-memory single-case research fixture; no production inventory persistence"}


def explicit_test_resources(run_id, patient_id):
    """Opt-in test factory. Runtime never calls this factory or assumes supplies."""
    return ResearchResourceFixture(run_id,patient_id,
        stock={"saline_500ml_bag":1,"blood_500ml_bag":1,"airway_kit":1,"occlusive_dressing_kit":1,"needle_kit":1},
        holds={"medic":1,"ventilator":1,"nasal_cannula":1,"oxygen_425l_source":1},
        capabilities=COSTS.keys(),permissions={"simulated_external_source_control","simulated_internal_source_control","iv_access"})
