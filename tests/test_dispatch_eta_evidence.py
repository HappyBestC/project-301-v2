"""Service-boundary regressions; all ETA responses are local test doubles."""
import asyncio

import pytest

from core301.dispatch.demo import demo_input, demo_eta
from core301.dispatch.models import CallFailure, EtaLegRequest, EtaResult
from core301.dispatch.manager import changed
from core301.dispatch.eta import EtaAdapter
from core301.dispatch.providers import FixedDispatchProvider
from core301.dispatch.validation import DispatchError
from core301.dispatch.service import decide_dispatch
from test_dispatch import context, proposal


@pytest.mark.parametrize("mode", ["evacuation", "team_response"])
def test_service_rejects_provider_without_eta(mode):
    class Provider:
        async def decide_dispatch(self, payload, callback):
            return proposal(mode)

    async def unexpected_eta(*args):
        pytest.fail("Service must not automatically query ETA")

    result = asyncio.run(decide_dispatch(context(), demo_input(), Provider(), unexpected_eta,
                                         ensure_active=lambda: None))
    assert isinstance(result, CallFailure)
    assert result.error.code == "DISPATCH_FAILED"

def routes(mode="evacuation", duration=12):
    source = demo_input()
    if mode == "onsite":
        return []
    team = mode == "team_response"
    first = EtaLegRequest(leg="team_to_patient" if team else "ambulance_to_patient",
        resource_id="TEAM-001" if team else "AMB-001",
        origin=source.medical_teams[0].position if team else source.ambulances[0].position,
        destination=source.position, departure_at_s=45)
    if team:
        return [first]
    return [first, EtaLegRequest(leg="patient_to_facility", resource_id="AMB-001",
        origin=source.position, destination=source.facilities[0].position, departure_at_s=45 + duration)]


def available(duration=12):
    return EtaResult(query_id="ETA-test", status="available", travel_duration_s=duration, detail=None)


def execute(requests, *, mode="evacuation", responses=None, swallow=False, source=None,
            mutate=None, ensure_active=lambda: None, external=None):
    source = source or demo_input()
    before = source.model_dump()
    calls = []
    values = iter(responses if responses is not None else [available() for _ in requests])

    class Provider:
        async def decide_dispatch(self, payload, callback):
            if mutate:
                mutate(payload)
            for request in requests:
                try:
                    await callback(request)
                except (Exception, asyncio.CancelledError):
                    if not swallow:
                        raise
            return proposal(mode)

    async def query(child, request):
        calls.append((child, request))
        assert child.run_id == source.run_id and child.patient_id == source.patient_id
        assert child.call_id != context().call_id
        if external:
            return await external(child, request)
        response = next(values)
        if isinstance(response, BaseException):
            raise response
        return response

    result = asyncio.run(decide_dispatch(context(), source, Provider(), query, ensure_active=ensure_active))
    assert source.model_dump() == before
    assert result.call_id == context().call_id
    if isinstance(result, CallFailure):
        assert result.error.run_id == source.run_id and result.error.patient_id == source.patient_id
    return result


def failure(result, code="DISPATCH_FAILED"):
    assert isinstance(result, CallFailure)
    assert result.error.code == code


@pytest.mark.parametrize("mode", ["onsite", "team_response", "evacuation"])
@pytest.mark.parametrize("duration", [0, 12])
def test_complete_evidence_and_zero_duration(mode, duration):
    requests = routes(mode, duration)
    result = execute(requests, mode=mode, responses=[available(duration) for _ in requests])
    assert result.data == proposal(mode)


@pytest.mark.parametrize("missing", [0, 1])
def test_evacuation_requires_both_legs(missing):
    requests = routes()
    requests.pop(missing)
    failure(execute(requests))


@pytest.mark.parametrize("mode,index", [("team_response", 0), ("evacuation", 0), ("evacuation", 1)])
@pytest.mark.parametrize("field", ["origin", "destination"])
@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_every_coordinate_must_match(mode, index, field, axis):
    requests = routes(mode)
    position = getattr(requests[index], field)
    requests[index] = changed(requests[index], **{field: changed(position, **{axis: getattr(position, axis) + 1})})
    failure(execute(requests, mode=mode))


@pytest.mark.parametrize("mode,index", [("team_response", 0), ("evacuation", 0), ("evacuation", 1)])
def test_different_resource_at_identical_coordinates_is_not_evidence(mode, index):
    source = demo_input()
    if mode == "team_response":
        source.medical_teams.append(changed(source.medical_teams[0], team_id="OTHER"))
    else:
        source.ambulances.append(changed(source.ambulances[0], ambulance_id="OTHER"))
    requests = routes(mode)
    requests[index] = changed(requests[index], resource_id="OTHER")
    failure(execute(requests, mode=mode, source=source))


def test_other_facility_is_not_evidence():
    requests = routes()
    requests[1] = changed(requests[1], destination=demo_input().facilities[1].position)
    failure(execute(requests))


@pytest.mark.parametrize("index", [0, 1])
def test_latest_departure_cannot_be_skipped(index):
    requests = routes()
    requests.append(changed(requests[index], departure_at_s=requests[index].departure_at_s + 1))
    failure(execute(requests))


def test_new_first_duration_invalidates_old_second_leg():
    requests = routes()
    failure(execute([*requests, requests[0]], responses=[available(), available(), available(20)]))


@pytest.mark.parametrize("mode,index", [("team_response", 0), ("evacuation", 0), ("evacuation", 1)])
def test_latest_unreachable_overrides_success(mode, index):
    requests = routes(mode)
    results = [available() for _ in requests]
    failure(execute([*requests, requests[index]], mode=mode, responses=[*results,
        EtaResult(query_id="later", status="unreachable", travel_duration_s=None, detail="closed")]),
        "RESOURCE_UNAVAILABLE")


def test_unrelated_unreachable_does_not_replace_selected_route():
    requests = routes()
    other = changed(requests[1], destination=demo_input().facilities[1].position)
    result = execute([*requests, other], responses=[available(), available(),
        EtaResult(query_id="other", status="unreachable", travel_duration_s=None, detail="closed")])
    assert result.data == proposal()
    failure(execute([other]))


@pytest.mark.parametrize("bad,code", [
    (EtaResult(query_id="failed", status="failed", travel_duration_s=None, detail="secret-external"), "ETA_FAILED"),
    ({"query_id": "bad", "status": "unknown", "travel_duration_s": 1, "detail": None}, "ETA_FAILED"),
    ({**available().model_dump(), "travel_duration_s": -1}, "ETA_FAILED"),
    ({**available().model_dump(), "travel_duration_s": float("nan")}, "ETA_FAILED"),
    ({**available().model_dump(), "travel_duration_s": float("inf")}, "ETA_FAILED"),
    (RuntimeError("secret-external"), "ETA_FAILED"),
    (TimeoutError("secret-external"), "ETA_TIMEOUT"),
    (DispatchError("ETA_TIMEOUT", "secret-external"), "ETA_TIMEOUT"),
    (DispatchError("ETA_FAILED", "secret-external"), "ETA_FAILED"),
])
@pytest.mark.parametrize("swallow", [False, True])
def test_terminal_failure_cannot_reuse_earlier_success(bad, code, swallow):
    requests = routes()
    result = execute([*requests, requests[0]], responses=[available(), available(), bad], swallow=swallow)
    failure(result, code)
    assert "secret-external" not in result.model_dump_json()


def test_backend_query_id_mismatch_is_latched():
    source = demo_input()
    class WrongAssociation:
        async def query(self, query):
            return available()  # Deliberately not the adapter-generated query_id.
    adapter = EtaAdapter(lambda: source, WrongAssociation(), lambda: None)
    failure(execute(routes(), external=adapter.query_eta, swallow=True), "ETA_FAILED")


@pytest.mark.parametrize("swallow", [False, True])
def test_cancelled_callback_never_becomes_success(swallow):
    with pytest.raises(asyncio.CancelledError):
        execute(routes(), responses=[asyncio.CancelledError()], swallow=swallow)


def test_stop_during_callback_cannot_be_swallowed():
    active = True
    def ensure_active():
        if not active:
            raise DispatchError("DISPATCH_FAILED", "stopped")
    async def query(child, request):
        nonlocal active
        await asyncio.sleep(0)
        active = False
        return available()
    failure(execute(routes(), external=query, ensure_active=ensure_active, swallow=True))


def test_provider_input_mutation_does_not_change_original_evidence_basis():
    requests = routes()
    requests[0] = changed(requests[0], origin=changed(requests[0].origin, z=99))
    def mutate(payload):
        payload.ambulances[0].position.z = 99
        payload.treatment_plan.actions.clear()
    failure(execute(requests, mutate=mutate))


def test_provider_cannot_rewrite_returned_result_or_request():
    source = demo_input()
    class Provider:
        async def decide_dispatch(self, payload, callback):
            first, second = routes()
            result = await callback(first)
            first.departure_at_s = 100
            result.travel_duration_s = 100
            await callback(second)
            return proposal()
    async def query(child, request):
        return available()
    result = asyncio.run(decide_dispatch(context(), source, Provider(), query, ensure_active=lambda: None))
    assert result.data == proposal()


def test_external_callback_cannot_rewrite_recorded_request():
    async def query(child, request):
        request.origin.z = 99
        return available()
    assert execute(routes(), external=query).data == proposal()


@pytest.mark.parametrize("mode", ["onsite", "team_response", "evacuation"])
def test_fixed_provider_regression(mode):
    source = demo_input()
    adapter = EtaAdapter(lambda: source, demo_eta(), lambda: None)
    result = asyncio.run(decide_dispatch(context(), source, FixedDispatchProvider(proposal(mode)),
        adapter.query_eta, ensure_active=lambda: None))
    assert result.data == proposal(mode)


def test_evidence_is_not_reused_between_service_calls():
    class CachingProvider:
        called = False
        async def decide_dispatch(self, payload, callback):
            if not self.called:
                for request in routes():
                    await callback(request)
                self.called = True
            return proposal()
    async def query(child, request):
        return available()
    async def run():
        provider = CachingProvider()
        first = await decide_dispatch(context(), demo_input(), provider, query, ensure_active=lambda: None)
        second = await decide_dispatch(context("CALL-002"), demo_input(), provider, query, ensure_active=lambda: None)
        assert first.data == proposal()
        failure(second)
    asyncio.run(run())


def test_actual_task_cancellation_survives_provider_catch():
    async def run():
        waiting = asyncio.Event()
        class Provider:
            async def decide_dispatch(self, payload, callback):
                try:
                    await callback(routes("team_response")[0])
                except asyncio.CancelledError:
                    pass
                return proposal("onsite")
        async def query(child, request):
            waiting.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(decide_dispatch(context(), demo_input(), Provider(), query,
                                                   ensure_active=lambda: None))
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())


def test_concurrent_completion_order_cannot_replace_latest_query():
    async def run():
        first_started, second_finished = asyncio.Event(), asyncio.Event()
        count = 0
        class Provider:
            async def decide_dispatch(self, payload, callback):
                first = asyncio.create_task(callback(routes("team_response")[0]))
                await first_started.wait()
                await callback(routes("team_response")[0])
                second_finished.set()
                await first
                return proposal("team_response")
        async def query(child, request):
            nonlocal count
            count += 1
            if count == 1:
                first_started.set()
                await second_finished.wait()
                return available()
            return EtaResult(query_id="latest", status="unreachable", travel_duration_s=None, detail="closed")
        result = await decide_dispatch(context(), demo_input(), Provider(), query, ensure_active=lambda: None)
        failure(result, "RESOURCE_UNAVAILABLE")
    asyncio.run(run())


def test_callback_cannot_be_used_after_dispatch_returns():
    async def run():
        class Provider:
            async def decide_dispatch(self, payload, callback):
                self.callback = callback
                return proposal("onsite")
        async def query(*args):
            pytest.fail("Closed callback must not query ETA")
        provider = Provider()
        result = await decide_dispatch(context(), demo_input(), provider, query, ensure_active=lambda: None)
        assert result.data == proposal("onsite")
        with pytest.raises(DispatchError, match="closed"):
            await provider.callback(routes()[0])
    asyncio.run(run())


def test_provider_dispatch_error_does_not_leak_external_details():
    class Provider:
        async def decide_dispatch(self, payload, callback):
            raise DispatchError("ETA_FAILED", "secret-external")
    async def query(*args):
        pytest.fail("Unexpected query")
    result = asyncio.run(decide_dispatch(context(), demo_input(), Provider(), query, ensure_active=lambda: None))
    failure(result, "ETA_FAILED")
    assert "secret-external" not in result.model_dump_json()
