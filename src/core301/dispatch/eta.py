from .complete_contracts import decode_dispatch_input
import asyncio
from typing import Protocol
from uuid import uuid4
from pydantic import TypeAdapter
from core301.contracts.base import Time
from .models import CallContext, DispatchInput, EtaLegRequest, EtaQuery, EtaResult
from .validation import DispatchError


class QueryEta(Protocol):
    async def __call__(self, payload: EtaLegRequest) -> EtaResult: ...


class EtaProvider(Protocol):
    async def query(self, query: EtaQuery) -> EtaResult: ...


def estimated_arrival(query, result):
    result = EtaResult.model_validate(result)
    if query.query_id != result.query_id:
        raise DispatchError("ETA_FAILED", "ETA query/result identity mismatch")
    if result.status != "available":
        raise DispatchError("ETA_FAILED", "ETA has no available duration")
    return TypeAdapter(Time).validate_python(query.departure_at_s + result.travel_duration_s, strict=True)


class EtaAdapter:
    """Backend boundary; injected provider can later wait for Unity instead of a fake."""
    def __init__(self, input_source, provider, ensure_active, *, timeout_s=None):
        if timeout_s is not None and (type(timeout_s) not in (int, float) or not 0 < timeout_s < float("inf")):
            raise ValueError("ETA transport timeout must be finite and positive")
        self.input_source, self.provider = input_source, provider
        self.ensure_active, self.timeout_s = ensure_active, timeout_s
        self.records = []
        self._call_ids = set()

    async def query_eta(self, context, payload):
        context = CallContext.model_validate(context)
        request = EtaLegRequest.model_validate(payload)
        self.ensure_active()
        source = decode_dispatch_input(self.input_source())
        if (context.run_id, context.patient_id) != (source.run_id, source.patient_id):
            raise DispatchError("ETA_FAILED", "ETA context identity mismatch")
        if context.call_id in self._call_ids:
            raise DispatchError("ETA_FAILED", "ETA subquery call_id already used")
        self._call_ids.add(context.call_id)
        is_team = request.leg == "team_to_patient"
        resources = source.medical_teams if is_team else source.ambulances
        key = "team_id" if is_team else "ambulance_id"
        resource = next((r for r in resources if getattr(r, key) == request.resource_id), None)
        if resource is None:
            raise DispatchError("ETA_FAILED", "ETA references an unknown resource or wrong resource type")
        if resource.active_task_id is not None:
            raise DispatchError("RESOURCE_UNAVAILABLE", "ETA resource is already assigned")
        if request.leg == "patient_to_facility":
            valid = request.origin == source.position and any(request.destination == f.position for f in source.facilities)
        else:
            valid = request.origin == resource.position and request.destination == source.position
        if not valid:
            raise DispatchError("ETA_FAILED", "ETA endpoints do not match this run's candidate locations")
        query = EtaQuery(**request.model_dump(), query_id=uuid4().hex, run_id=context.run_id, patient_id=context.patient_id)
        record = {"context": context.model_dump(), "query": query.model_dump()}
        self.records.append(record)
        try:
            pending = self.provider.query(query)
            result = await pending if self.timeout_s is None else await asyncio.wait_for(pending, self.timeout_s)
            self.ensure_active()  # Stopped-run replies must not resume scheduling.
            result = EtaResult.model_validate(result)
            if result.query_id != query.query_id:
                raise DispatchError("ETA_FAILED", "ETA query/result identity mismatch")
            record["result"] = result.model_dump()
            if result.status == "failed":
                raise DispatchError("ETA_FAILED", result.detail)
            return result  # unreachable is a valid reply, never a zero-duration route.
        except TimeoutError:
            record["error_code"] = "ETA_TIMEOUT"
            raise DispatchError("ETA_TIMEOUT", "ETA transport wait exceeded configured limit") from None
        except DispatchError as exc:
            record["error_code"] = exc.code
            raise
        except Exception:
            record["error_code"] = "ETA_FAILED"
            raise DispatchError("ETA_FAILED", "ETA provider returned invalid data or failed") from None


class FakeEtaProvider:
    """Explicit scenario durations only; no speed or geometry-to-time assumptions."""
    def __init__(self, routes):
        self.routes = routes

    @staticmethod
    def key(query):
        return (query.leg, query.resource_id, query.destination.x, query.destination.y, query.destination.z)

    async def query(self, query):
        status, duration, detail = self.routes.get(self.key(query), ("failed", None, "fake route not configured"))
        return EtaResult(query_id=query.query_id, status=status, travel_duration_s=duration, detail=detail)
