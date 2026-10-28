from typing import Protocol
from core301.contracts.treatment import TreatmentPlan
from .models import DispatchInput, DispatchProposal, ActionType


class DispatchError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class OnsiteCapabilitySource(Protocol):
    def __call__(self, payload: DispatchInput) -> frozenset[ActionType] | None: ...


def required_action_types(plan):
    return frozenset(a.action_type for a in TreatmentPlan.model_validate(plan).actions)


def validate_proposal(payload, proposal, *, onsite_capability=None, input_model=DispatchInput,
                      required_actions=required_action_types, action_types=None):
    payload = input_model.model_validate(payload)
    # Validate the exact proposal, rejecting DispatchTask instances and injected fields too.
    proposal = DispatchProposal.model_validate(proposal.model_dump() if hasattr(proposal, "model_dump") else proposal)
    if proposal.patient_id != payload.patient_id:
        raise DispatchError("DISPATCH_FAILED", "proposal patient identity mismatch")
    required = required_actions(payload.treatment_plan)

    def select(items, key, value):
        resource = next((r for r in items if getattr(r, key) == value), None)
        if resource is None:
            raise DispatchError("DISPATCH_FAILED", "selected resource is not in DispatchInput")
        return resource

    def capable(resource):
        if not required <= set(resource.supported_action_types):
            raise DispatchError("RESOURCE_UNAVAILABLE", "selected resource cannot cover the complete treatment plan")

    if proposal.mode == "team_response":
        team = select(payload.medical_teams, "team_id", proposal.team_id)
        if team.active_task_id is not None:
            raise DispatchError("RESOURCE_UNAVAILABLE", "medical team already has an active task")
        capable(team)
    elif proposal.mode == "evacuation":
        ambulance = select(payload.ambulances, "ambulance_id", proposal.ambulance_id)
        facility = select(payload.facilities, "facility_id", proposal.target_facility_id)
        if ambulance.active_task_id is not None:
            raise DispatchError("RESOURCE_UNAVAILABLE", "ambulance already has an active task")
        if facility.remaining_capacity <= 0:
            raise DispatchError("RESOURCE_UNAVAILABLE", "facility has no remaining capacity")
        capable(facility)
    elif payload.current_facility_id is not None:
        facility = select(payload.facilities, "facility_id", payload.current_facility_id)
        if payload.patient_id not in facility.admitted_patient_ids:
            raise DispatchError("RESOURCE_UNAVAILABLE", "current facility has not confirmed patient admission")
        capable(facility)  # Existing admission already occupies capacity; no second reservation.
    else:
        capabilities = onsite_capability(payload) if onsite_capability is not None else None
        if capabilities is None:
            raise DispatchError("RESOURCE_UNAVAILABLE", "onsite capability source / mapping is not confirmed")
        from pydantic import TypeAdapter
        if action_types is None:
            capabilities = TypeAdapter(list[ActionType]).validate_python(list(capabilities), strict=True)
        elif not set(capabilities) <= set(action_types):
            raise DispatchError("RESOURCE_UNAVAILABLE", "unknown onsite capability")
        if not required <= set(capabilities):
            raise DispatchError("RESOURCE_UNAVAILABLE", "onsite capabilities do not cover the complete plan")
    return proposal
