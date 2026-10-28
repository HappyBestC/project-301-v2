import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core301.contracts.observation import PatientObservation
from core301.contracts.treatment import TreatmentPlan, ACTION_TYPES
from core301.dispatch.clock import SimulationClock
from core301.dispatch.demo import demo_input, demo_eta
from core301.dispatch.eta import EtaAdapter, FakeEtaProvider, estimated_arrival
from core301.dispatch.events import EventTransition
from core301.dispatch.manager import ResourceManager, changed
from core301.dispatch.models import (Position, Facility, Ambulance, MedicalTeam, DispatchInput, DispatchProposal,
    DispatchTask, TaskEvent, EtaLegRequest, EtaQuery, EtaResult, CallContext, CallFailure)
from core301.dispatch.providers import FixedDispatchProvider
from core301.dispatch.service import decide_dispatch
from core301.dispatch.validation import DispatchError, validate_proposal, required_action_types


@pytest.fixture
def source(): return demo_input()


def proposal(mode="evacuation", **overrides):
    data = {"patient_id": "P-001", "mode": mode, "team_id": "TEAM-001" if mode == "team_response" else None,
            "ambulance_id": "AMB-001" if mode == "evacuation" else None,
            "target_facility_id": "FAC-001" if mode == "evacuation" else None}
    return DispatchProposal.model_validate({**data, **overrides})


def context(call="CALL-001"):
    return CallContext(call_id=call, run_id="RUN-DEMO", patient_id="P-001")


def task(mode="evacuation", **updates):
    return DispatchTask.model_validate({**proposal(mode).model_dump(), "task_id": "TASK-001", "run_id": "RUN-DEMO",
        "state": "assigned", "accepted_at_s": 45, "treatment_ready_at_s": 45 if mode == "onsite" else None,
        "ended_at_s": None, "detail": None, **updates})


@pytest.mark.parametrize("value", [True, False, "1", None, float("nan"), float("inf"), -float("inf")])
def test_position_strict(value):
    with pytest.raises(ValidationError): Position(x=value, y=0, z=0)


def test_position_negative_and_ids_preserved(source):
    assert Position(x=-1, y=0, z=2.5).x == -1
    assert changed(source.facilities[0], facility_id=" F ").facility_id == " F "
    with pytest.raises(ValidationError): Position(x=0, y=0, z=0, latitude=1)
    with pytest.raises(ValidationError): changed(source.facilities[0], display_name=" \t")


@pytest.mark.parametrize("capacity", [-1, "2", True, None, 2.0])
def test_capacity_strict(source, capacity):
    with pytest.raises(ValidationError): changed(source.facilities[0], capacity=capacity)


@pytest.mark.parametrize("updates", [
    {"kind": "clinic"}, {"supported_action_types": ["unknown"]},
    {"supported_action_types": ["transfusion", "transfusion"]},
    {"reserved_patient_ids": ["P", "P"]}, {"admitted_patient_ids": ["P", "P"]},
    {"reserved_patient_ids": ["P"], "admitted_patient_ids": ["P"]},
    {"reserved_patient_ids": ["A", "B"], "admitted_patient_ids": ["C"]},
    {"available_capacity": 2}, {"blood_inventory": 10},
])
def test_facility_invariants(source, updates):
    with pytest.raises(ValidationError): changed(source.facilities[0], **updates)


def test_facility_capacity_and_action_enum_reused(source):
    facility = changed(source.facilities[0], supported_action_types=list(ACTION_TYPES), reserved_patient_ids=["P-002"])
    assert facility.remaining_capacity == 1
    assert "remaining_capacity" not in facility.model_dump()
    assert changed(facility, kind="hospital", capacity=1).remaining_capacity == 0
    assert changed(source.facilities[0], capacity=0).remaining_capacity == 0
    assert Facility.model_json_schema()["properties"]["supported_action_types"]["items"]["enum"] == list(ACTION_TYPES)


@pytest.mark.parametrize("kind", ["ambulances", "medical_teams"])
def test_active_task_id_required_nullable_not_busy(source, kind):
    resource = getattr(source, kind)[0]
    assert resource.active_task_id is None
    assert changed(resource, active_task_id="TASK-9").active_task_id == "TASK-9"
    for changes in ({"active_task_id": " "}, {"busy": True}, {"active_task_id": False}):
        with pytest.raises(ValidationError): changed(resource, **changes)
    missing = resource.model_dump()
    missing.pop("active_task_id")
    with pytest.raises(ValidationError): type(resource).model_validate(missing)


def test_no_implicit_defaults(source):
    for model in [source, source.facilities[0], source.ambulances[0], source.medical_teams[0], proposal(), task(), context()]:
        for key in type(model).model_fields:
            data = model.model_dump()
            data.pop(key)
            with pytest.raises(ValidationError): type(model).model_validate(data)


@pytest.mark.parametrize("field", ["severity", "CasualtyInput", "raw_state", "counterfactual_observation", "TreatmentEvaluation", "treatment_priority", "evacuation_priority"])
def test_dispatch_input_forbids_extra_fields(source, field):
    with pytest.raises(ValidationError): changed(source, **{field: 1})


def test_input_reuses_frozen_models_and_cross_references(source):
    assert DispatchInput.model_fields["patient_observation"].annotation is PatientObservation
    assert DispatchInput.model_fields["treatment_plan"].annotation is TreatmentPlan
    data = source.model_dump()
    for path in ("patient_observation", "treatment_plan"):
        bad = deepcopy(data)
        bad[path]["patient_id"] = "other"
        with pytest.raises(ValidationError): DispatchInput.model_validate(bad)
    for kind in ("facilities", "ambulances", "medical_teams"):
        bad = deepcopy(data)
        bad[kind][0]["run_id"] = "another run"
        with pytest.raises(ValidationError): DispatchInput.model_validate(bad)
        bad = deepcopy(data)
        bad[kind].append(deepcopy(bad[kind][0]))
        with pytest.raises(ValidationError): DispatchInput.model_validate(bad)
    assert changed(source, facilities=[], ambulances=[], medical_teams=[]).facilities == []


@pytest.mark.parametrize("mode", ["onsite", "team_response", "evacuation"])
def test_proposal_valid_modes(mode):
    assert proposal(mode).mode == mode


@pytest.mark.parametrize("mode,fields", [
    ("onsite", {"team_id": "TEAM-001"}), ("onsite", {"target_facility_id": "FAC-001"}),
    ("team_response", {"ambulance_id": "AMB-001"}), ("team_response", {"team_id": None}),
    ("evacuation", {"target_facility_id": None}), ("evacuation", {"ambulance_id": None}),
    ("evacuation", {"team_id": "TEAM-001"}), ("invalid", {}),
])
def test_invalid_proposal_combinations(mode, fields):
    with pytest.raises(ValidationError): proposal(mode, **fields)


@pytest.mark.parametrize("field", ["task_id", "state", "accepted_at_s", "treatment_ready_at_s", "ended_at_s", "treatment_plan", "resource_mutation", "treatment_priority", "evacuation_priority"])
def test_proposal_rejects_agent_overreach(field):
    with pytest.raises(ValidationError): changed(proposal(), **{field: "forbidden"})


def test_selection_ids_capabilities_and_patient(source):
    assert validate_proposal(source, proposal()) == proposal()
    for p in [proposal(patient_id="other"), proposal(ambulance_id="fabricated"), proposal(target_facility_id="fabricated"),
              proposal("team_response", team_id="fabricated")]:
        with pytest.raises(DispatchError) as exc: validate_proposal(source, p)
        assert exc.value.code == "DISPATCH_FAILED"
    data = source.model_dump()
    data["facilities"][0]["supported_action_types"] = []
    with pytest.raises(DispatchError, match="cover"): validate_proposal(data, proposal())
    data = source.model_dump()
    data["medical_teams"][0]["supported_action_types"] = []
    with pytest.raises(DispatchError, match="cover"): validate_proposal(data, proposal("team_response"))
    plan = TreatmentPlan(patient_id="P", actions=[{"action_type": "chest_tube", "side": "Left"}, {"action_type": "chest_tube", "side": "Right"}])
    assert required_action_types(plan) == {"chest_tube"}


@pytest.mark.parametrize("kind,mode", [("ambulances", "evacuation"), ("medical_teams", "team_response")])
def test_busy_resources_rejected(source, kind, mode):
    data = source.model_dump()
    data[kind][0]["active_task_id"] = "other-task"
    with pytest.raises(DispatchError) as exc: validate_proposal(data, proposal(mode))
    assert exc.value.code == "RESOURCE_UNAVAILABLE"


def test_full_facility_and_onsite_current_admission(source):
    data = source.model_dump()
    data["facilities"][0]["capacity"] = 1
    data["facilities"][0]["admitted_patient_ids"] = [source.patient_id]
    data["current_facility_id"] = "FAC-001"
    with pytest.raises(DispatchError, match="capacity"): validate_proposal(data, proposal())
    assert validate_proposal(data, proposal("onsite")).mode == "onsite"


def test_field_onsite_requires_explicit_capability_source(source):
    with pytest.raises(DispatchError, match="not confirmed"): validate_proposal(source, proposal("onsite"))
    with pytest.raises(DispatchError, match="do not cover"):
        validate_proposal(source, proposal("onsite"), onsite_capability=lambda _: frozenset())
    assert validate_proposal(source, proposal("onsite"), onsite_capability=lambda _: frozenset(["fluid_resuscitation"]))


@pytest.mark.parametrize("status,duration,detail", [("available", 0, None), ("available", 12.5, None),
    ("unreachable", None, "blocked"), ("failed", None, "calculator failed")])
def test_eta_result_valid(status, duration, detail):
    assert EtaResult(query_id="Q", status=status, travel_duration_s=duration, detail=detail).status == status


@pytest.mark.parametrize("status,duration,detail", [("failed", 0, "error"), ("unreachable", 0, "error"),
    ("available", None, None), ("available", -1, None), ("available", True, None), ("available", "3", None),
    ("available", float("inf"), None), ("available", 1, "unexpected"), ("failed", None, " ")])
def test_eta_result_invalid(status, duration, detail):
    with pytest.raises(ValidationError): EtaResult(query_id="Q", status=status, travel_duration_s=duration, detail=detail)


def leg(source, **updates):
    return EtaLegRequest.model_validate({"leg": "ambulance_to_patient", "resource_id": "AMB-001",
        "origin": source.ambulances[0].position.model_dump(), "destination": source.position.model_dump(), "departure_at_s": 45, **updates})


def test_eta_exact_leg_fields_and_time_addition(source):
    request = leg(source)
    assert set(request.model_dump()) == {"leg", "resource_id", "origin", "destination", "departure_at_s"}
    with pytest.raises(ValidationError): changed(request, query_id="agent-guessed")
    query = EtaQuery(**request.model_dump(), query_id="Q", run_id=source.run_id, patient_id=source.patient_id)
    result = EtaResult(query_id="Q", status="available", travel_duration_s=12, detail=None)
    assert estimated_arrival(query, result) == 57
    with pytest.raises(DispatchError): estimated_arrival(query, changed(result, query_id="wrong"))


def test_eta_adapter_queries_and_two_leg_departure(source):
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
        response = await decide_dispatch(context(), source, FixedDispatchProvider(proposal()), eta.query_eta, ensure_active=manager.ensure_active)
        assert response.data == proposal()
        first, second = eta.records
        assert first["query"]["departure_at_s"] == 45
        assert second["query"]["departure_at_s"] == 57
        assert second["query"]["origin"] == source.position.model_dump()
        assert first["context"]["call_id"] != second["context"]["call_id"] != context().call_id
        assert first["query"]["query_id"] != second["query"]["query_id"]
        assert manager.snapshot() == source  # ETA/predictions do not reserve or execute anything.
    asyncio.run(run())


@pytest.mark.parametrize("status,code", [("failed", "ETA_FAILED"), ("unreachable", "RESOURCE_UNAVAILABLE")])
def test_eta_unavailable_not_zero_or_fallback(source, status, code):
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        fake = FakeEtaProvider({("ambulance_to_patient", "AMB-001", 10, 0, 20): (status, None, "test reason")})
        eta = EtaAdapter(manager.snapshot, fake, manager.ensure_active)
        response = await decide_dispatch(context(), source, FixedDispatchProvider(proposal()), eta.query_eta, ensure_active=manager.ensure_active)
        assert isinstance(response, CallFailure) and response.error.code == code
        assert len(eta.records) == 1 and manager.snapshot() == source
    asyncio.run(run())


def test_eta_wrong_endpoints_type_and_query_identity(source):
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
        for i, updates in enumerate([{"resource_id": "TEAM-001"}, {"destination": {"x": 999, "y": 0, "z": 0}}]):
            with pytest.raises(DispatchError): await eta.query_eta(context(str(i)), leg(source, **updates))
        async def wrong(query): return EtaResult(query_id="wrong", status="available", travel_duration_s=0, detail=None)
        eta.provider = SimpleNamespace(query=wrong)
        with pytest.raises(DispatchError, match="identity"): await eta.query_eta(context("third"), leg(source))
    asyncio.run(run())


def test_eta_timeout_and_late_reply_do_not_resume(source):
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        async def slow(query):
            await asyncio.sleep(1)
        eta = EtaAdapter(manager.snapshot, SimpleNamespace(query=slow), manager.ensure_active, timeout_s=0.001)
        with pytest.raises(DispatchError) as exc: await eta.query_eta(context(), leg(source))
        assert exc.value.code == "ETA_TIMEOUT"
        async def late(query):
            manager.stop_run()
            return EtaResult(query_id=query.query_id, status="available", travel_duration_s=0, detail=None)
        eta.provider = SimpleNamespace(query=late)
        with pytest.raises(DispatchError, match="no longer active"): await eta.query_eta(context("later"), leg(source))
        assert manager.snapshot() == source
    asyncio.run(run())


@pytest.mark.parametrize("updates", [
    {"state": "completed"}, {"state": "failed", "ended_at_s": 50, "detail": None},
    {"state": "cancelled", "ended_at_s": 44, "detail": "cancel"},
    {"detail": "not allowed"}, {"treatment_ready_at_s": 44}, {"ended_at_s": 50},
])
def test_task_temporal_and_detail_constraints(updates):
    with pytest.raises(ValidationError): task(**updates)


def test_task_modes_and_event_schema():
    with pytest.raises(ValidationError): task("onsite", treatment_ready_at_s=None)
    with pytest.raises(ValidationError): task("team_response", state="transporting")
    with pytest.raises(ValidationError): TaskEvent(event_id="E", run_id="R", task_id="T", kind="completed", occurred_at_s=1, position=Position(x=0,y=0,z=0))
    with pytest.raises(ValidationError): task(priority="high")


def test_accept_reserves_once_and_only_backend_mutates(source):
    manager = ResourceManager(source, SimulationClock(45))
    before = source.model_dump()
    created = manager.accept(context(), source, proposal())
    current = manager.snapshot()
    assert created.state == "assigned" and created.accepted_at_s == 45 and created.treatment_ready_at_s is None
    assert current.facilities[0].reserved_patient_ids == [source.patient_id]
    assert current.facilities[0].remaining_capacity == 1
    assert current.ambulances[0].active_task_id == created.task_id
    assert source.model_dump() == before
    assert manager.accept(context(), source, proposal()).task_id == created.task_id
    with pytest.raises(DispatchError): manager.accept(context("another"), source, proposal())
    assert manager.snapshot() == current
    # Returned views are detached; callers cannot mutate authoritative accounting.
    current.facilities[0].reserved_patient_ids.clear()
    assert manager.snapshot().facilities[0].reserved_patient_ids == [source.patient_id]


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_failure_or_cancel_releases_reservation_and_vehicle(source, state):
    manager = ResourceManager(source, SimulationClock(45))
    created = manager.accept(context(), source, proposal())
    manager.clock.advance_to(50)
    ended = manager.terminate(created.task_id, state=state, detail="backend confirmed")
    current = manager.snapshot()
    assert ended.ended_at_s == 50 and ended.state == state
    assert current.facilities[0].reserved_patient_ids == []
    assert current.ambulances[0].active_task_id is None
    assert current.ambulances[0].position == source.ambulances[0].position


class FixtureEventPolicy:
    """TEST ONLY: illustrative API04/position policy, not a supplied formal MR5 table."""
    def __call__(self, task, event, patient_position, facility_position):
        rules = {("assigned", "departed"): "to_patient", ("to_patient", "arrived_at_patient"): "at_patient",
                 ("at_patient", "transport_started"): "transporting", ("transporting", "arrived_at_facility"): "at_facility"}
        state = rules.get((task.state, event.kind))
        if state is None:
            raise DispatchError("DISPATCH_FAILED", "fixture event is out of sequence")
        if event.kind in ("arrived_at_patient", "transport_started") and event.position != patient_position:
            raise DispatchError("DISPATCH_FAILED", "fixture patient position mismatch")
        if event.kind == "arrived_at_facility" and event.position != facility_position:
            raise DispatchError("DISPATCH_FAILED", "fixture facility position mismatch")
        return EventTransition(state, task.mode == "team_response" and event.kind == "arrived_at_patient")


def event(manager, task_id, kind, time, position, event_id=None):
    manager.clock.advance_to(time)
    value = TaskEvent(event_id=event_id or kind, task_id=task_id, run_id=manager.run_id, kind=kind, occurred_at_s=time, position=position)
    return value, manager.apply_event(value)


def test_admission_requires_backend_confirmation_and_preserves_capacity_until_episode_end(source):
    manager = ResourceManager(source, SimulationClock(45), event_policy=FixtureEventPolicy())
    created = manager.accept(context(), source, proposal())
    event(manager, created.task_id, "departed", 45, source.ambulances[0].position)
    previous, _ = event(manager, created.task_id, "arrived_at_patient", 57, source.position)
    event(manager, created.task_id, "transport_started", 57, source.position)
    event(manager, created.task_id, "arrived_at_facility", 92, source.facilities[0].position)
    assert manager.snapshot().facilities[0].reserved_patient_ids == [source.patient_id]
    assert manager.snapshot().ambulances[0].active_task_id == created.task_id
    assert manager.task(created.task_id).treatment_ready_at_s is None
    # A duplicate old event returns its prior receipt without rewinding the task.
    assert manager.apply_event(previous).state == "at_patient"
    assert manager.task(created.task_id).state == "at_facility"
    manager.clock.advance_to(93)
    done = manager.confirm_facility_admission(created.task_id)
    assert done.state == "completed" and done.treatment_ready_at_s == 93
    current = manager.snapshot()
    assert current.facilities[0].reserved_patient_ids == [] and current.facilities[0].admitted_patient_ids == [source.patient_id]
    assert current.facilities[0].remaining_capacity == 1 and current.ambulances[0].active_task_id is None
    assert current.current_facility_id == "FAC-001"
    manager.end_episode()
    assert manager.snapshot().facilities[0].admitted_patient_ids == []
    assert manager.snapshot().position == source.facilities[0].position
    assert manager.snapshot().current_facility_id == "FAC-001"  # Historical location is retained.


def test_team_does_not_use_ambulance_and_stays_assigned_until_episode_end(source):
    manager = ResourceManager(source, SimulationClock(45), event_policy=FixtureEventPolicy())
    created = manager.accept(context(), source, proposal("team_response"))
    event(manager, created.task_id, "departed", 45, source.medical_teams[0].position)
    event(manager, created.task_id, "arrived_at_patient", 63, source.position)
    assert manager.snapshot().medical_teams[0].active_task_id == created.task_id
    assert manager.snapshot().ambulances == source.ambulances
    manager.end_episode(unfinished_task_outcome="completed")
    assert manager.task(created.task_id).state == "completed"
    assert manager.snapshot().medical_teams[0].active_task_id is None
    assert manager.snapshot().medical_teams[0].position == source.position


def test_onsite_confirmation_is_not_pulse_success(source):
    manager = ResourceManager(source, SimulationClock(45), onsite_capability=lambda _: frozenset(["fluid_resuscitation"]))
    created = manager.accept(context(), source, proposal("onsite"))
    assert created.treatment_ready_at_s == created.accepted_at_s
    done = manager.confirm_onsite(created.task_id)
    assert done.state == "completed"
    assert "treatment_success" not in done.model_dump()
    assert manager.snapshot() == source


def test_no_event_policy_does_not_invent_one(source):
    manager = ResourceManager(source, SimulationClock(45))
    created = manager.accept(context(), source, proposal())
    with pytest.raises(DispatchError, match="API04"):
        event(manager, created.task_id, "departed", 45, source.ambulances[0].position)
    assert manager.task(created.task_id).state == "assigned"
    with pytest.raises(DispatchError): manager.confirm_facility_admission(created.task_id)


def test_events_reject_cross_run_future_wrong_order_and_conflicting_replay(source):
    manager = ResourceManager(source, SimulationClock(45), event_policy=FixtureEventPolicy())
    created = manager.accept(context(), source, proposal())
    e = TaskEvent(event_id="E", task_id=created.task_id, run_id=source.run_id, kind="departed", occurred_at_s=45, position=source.ambulances[0].position)
    for bad in [changed(e, run_id="other"), changed(e, occurred_at_s=46), changed(e, kind="arrived_at_facility")]:
        with pytest.raises(DispatchError): manager.apply_event(bad)
    manager.apply_event(e)
    with pytest.raises(DispatchError): manager.apply_event(changed(e, position=source.position.model_dump()))
    assert manager.task(created.task_id).state == "to_patient"


def test_manager_rejects_unknown_active_task_and_unknown_patient_references(source):
    data = source.model_dump()
    data["ambulances"][0]["active_task_id"] = "nonexistent"
    with pytest.raises(ValueError, match="active_task_id"): ResourceManager(data, SimulationClock(45))
    data = source.model_dump()
    data["facilities"][0]["admitted_patient_ids"] = ["other"]
    with pytest.raises(ValueError, match="patient references"): ResourceManager(data, SimulationClock(45))


def test_fresh_backend_state_overrules_stale_input(source):
    manager = ResourceManager(source, SimulationClock(45))
    # Simulate a separately confirmed backend admission while the provider was waiting.
    manager._facilities["FAC-001"] = changed(manager._facilities["FAC-001"], capacity=0)
    before = manager.snapshot()
    with pytest.raises(DispatchError, match="capacity"): manager.accept(context(), source, proposal())
    assert manager.snapshot() == before and manager._tasks == {}


def test_simulation_clock_strict_and_monotonic():
    for bad in [-1, True, "1", float("nan"), float("inf")]:
        with pytest.raises(ValidationError): SimulationClock(bad)
    clock = SimulationClock(45)
    clock.advance_to(57)
    assert clock.now_s == 57
    with pytest.raises(ValueError): clock.advance_to(56)


def test_provider_cannot_mutate_backend_plan_and_context_stays_out(source):
    class MutatingProvider:
        async def decide_dispatch(self, payload, query_eta):
            assert set(payload.model_dump()) == set(DispatchInput.model_fields)
            await FixedDispatchProvider(proposal()).decide_dispatch(payload, query_eta)
            payload.treatment_plan.actions.clear()
            return proposal()
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        before = source.model_dump()
        eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
        response = await decide_dispatch(context(), source, MutatingProvider(), eta.query_eta, ensure_active=manager.ensure_active)
        assert response.data == proposal() and source.model_dump() == before
        assert manager.snapshot().treatment_plan == source.treatment_plan
    asyncio.run(run())


def test_backend_cannot_confirm_or_cancel_another_patients_task(source):
    foreign = task(patient_id="P-002", state="at_facility")
    data = source.model_dump()
    data["ambulances"][0]["active_task_id"] = foreign.task_id
    data["facilities"][0]["reserved_patient_ids"] = ["P-002"]
    manager = ResourceManager(data, SimulationClock(45), known_patient_ids=["P-002"], tasks=[foreign])
    before = manager.snapshot()
    with pytest.raises(DispatchError, match="does not own"):
        manager.confirm_facility_admission(foreign.task_id)
    with pytest.raises(DispatchError, match="does not own"):
        manager.terminate(foreign.task_id, state="cancelled", detail="wrong patient")
    assert manager.snapshot() == before


def test_accept_context_and_plan_replacement_rejected(source):
    manager = ResourceManager(source, SimulationClock(45))
    for ctx in [changed(context(), run_id="other"), changed(context(), patient_id="other")]:
        with pytest.raises(DispatchError, match="identity"): manager.accept(ctx, source, proposal())
    revised = changed(source, treatment_plan={"patient_id": source.patient_id, "actions": []})
    with pytest.raises(DispatchError, match="replace"): manager.accept(context(), revised, proposal())
    assert manager.snapshot() == source


def test_missing_failure_detail_does_not_partially_release(source):
    manager = ResourceManager(source, SimulationClock(45))
    created = manager.accept(context(), source, proposal())
    before = manager.snapshot()
    with pytest.raises(ValidationError): manager.terminate(created.task_id, state="failed", detail="")
    assert manager.task(created.task_id).state == "assigned" and manager.snapshot() == before


def test_late_provider_reply_after_stop_rejected(source):
    async def run():
        manager = ResourceManager(source, SimulationClock(45))
        class LateProvider:
            async def decide_dispatch(self, payload, query_eta):
                manager.stop_run()
                return proposal()
        eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
        result = await decide_dispatch(context(), source, LateProvider(), eta.query_eta, ensure_active=manager.ensure_active)
        assert isinstance(result, CallFailure)
        assert manager.snapshot() == source and manager._tasks == {}
    asyncio.run(run())
