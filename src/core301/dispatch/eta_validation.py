"""Validate invocation-local ETA evidence against the original dispatch snapshot."""
from .validation import DispatchError


def validate_eta_evidence(source, proposal, records):
    if proposal.mode == "onsite":
        return
    if proposal.mode == "team_response":
        resource = next((r for r in source.medical_teams if r.team_id == proposal.team_id), None)
        first_leg, resource_id = "team_to_patient", proposal.team_id
    else:
        resource = next((r for r in source.ambulances if r.ambulance_id == proposal.ambulance_id), None)
        first_leg, resource_id = "ambulance_to_patient", proposal.ambulance_id
    if resource is None:
        raise DispatchError("DISPATCH_FAILED", "selected ETA resource is absent from input")
    routes = [(first_leg, resource_id, resource.position, source.position)]
    if proposal.mode == "evacuation":
        facility = next((f for f in source.facilities if f.facility_id == proposal.target_facility_id), None)
        if facility is None:
            raise DispatchError("DISPATCH_FAILED", "selected ETA facility is absent from input")
        routes.append(("patient_to_facility", resource_id, source.position, facility.position))

    # Match geometry and identity first, then validate the latest record's time.
    # Including departure time in the lookup would allow stale successes to win.
    selected = []
    for route in routes:
        selected.append(next(((request, result) for request, result in reversed(records)
                              if (request.leg, request.resource_id, request.origin, request.destination) == route), None))
    if any(record is not None and record[1].status == "unreachable" for record in selected):
        raise DispatchError("RESOURCE_UNAVAILABLE", "selected route was reported unreachable")
    if any(record is None for record in selected):
        raise DispatchError("DISPATCH_FAILED", "missing matching ETA evidence for selected route")
    departure = source.patient_observation.simulation_time_s
    for request, result in selected:
        if result.status != "available" or request.departure_at_s != departure:
            raise DispatchError("DISPATCH_FAILED", "selected ETA evidence has inconsistent departure time")
        departure += result.travel_duration_s
