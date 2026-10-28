from core301.pulse.v2.protocol_book import ALLOWED_ACTIONS, OPEN_INJURIES, PROFILE_VERSION, protocol_id
from .errors import V2Error

REQUIRED_MONITORS={
    "external_hemorrhage":("vitals.mean_arterial_pressure","circulation.cardiac_output","laboratory.hemoglobin_concentration"),
    "abdominal_internal_hemorrhage":("vitals.mean_arterial_pressure","circulation.cardiac_output","laboratory.hemoglobin_concentration"),
    "open_pneumothorax":("respiratory.tidal_volume","laboratory.arterial_oxygen_pressure"),
    "closed_tension_pneumothorax":("respiratory.tidal_volume","laboratory.arterial_oxygen_pressure"),
    "respiratory_muscle_impairment":("respiratory.tidal_volume","laboratory.arterial_carbon_dioxide_pressure","laboratory.blood_ph"),
    "impaired_alveolar_exchange":("respiratory.inspired_oxygen_fraction","laboratory.arterial_oxygen_pressure","laboratory.arterial_carbon_dioxide_pressure","laboratory.blood_ph"),
    "dehydration":("vitals.mean_arterial_pressure","circulation.cardiac_output","laboratory.hemoglobin_concentration"),
}


def validate_capability(plan, public_context, registry, registry_signature, mode, resources):
    if plan.patient_id!=public_context.patient_id or plan.patient_id!=registry.patient_id:
        raise V2Error("PATIENT_MISMATCH", "Treatment/context/registry patient mismatch")
    if registry.signature()!=registry_signature:
        raise V2Error("STALE_SOURCE", "Context source version is stale")
    if len(registry.sources())!=1:
        raise V2Error("UNVALIDATED_MULTISOURCE", "Only one authoritative source is open in phase 1")
    source,=registry.sources()
    if not source.active or not source.authorized:
        raise V2Error("TARGET_NOT_AUTHORIZED", "Source is inactive or revoked")
    scope=OPEN_INJURIES.get(source.injury_type)
    if scope is None or source.initial_severity not in scope[0] or (scope[1] and getattr(source,scope[1])!=scope[2]):
        raise V2Error("UNVALIDATED_SCOPE", "Registry source is outside the immutable protocol scope")
    if mode!="research":
        raise V2Error("PRODUCTION_NOT_ENABLED", "Phase-1 protocol profiles are research-only")
    if plan.actions and (resources is None or resources.authority_kind!="explicit_research_fixture"):
        raise V2Error("RESOURCE_AUTHORITY_MISSING", "Research execution needs an explicit bound resource credential")
    if plan.actions:
        observation=public_context.patient_observation
        for path in REQUIRED_MONITORS[source.injury_type]:
            group,field=path.split(".")
            measurement=getattr(getattr(observation,group,None),field,None)
            if measurement is None or measurement.status!="available" or measurement.value is None or measurement.observed_at_s!=observation.simulation_time_s:
                raise V2Error("MONITORING_UNAVAILABLE", "Required authorized, acquired, current public safety measurements are missing")
    known=[i.model_dump() for i in public_context.known_injuries]
    protocols=[]
    for action in plan.actions:
        if action.action_type not in ALLOWED_ACTIONS.get(source.injury_type,()):
            raise V2Error("ACTION_NOT_OPEN", "Injury/action protocol is not open in phase 1")
        target=source.known()
        if target not in known or any(getattr(action,k,None)!=getattr(source,k,None) for k in ("side","compartment") if hasattr(action,k)):
            raise V2Error("TARGET_NOT_AUTHORIZED", "Action must match an explicitly authorized injury and position")
        protocols.append(protocol_id(source.injury_type,action.action_type))
    return source,protocols,PROFILE_VERSION
