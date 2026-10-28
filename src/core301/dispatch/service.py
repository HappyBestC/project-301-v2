from .complete_contracts import decode_dispatch_input
"""INT03 association boundary. Context is never included in the model's messages."""
from uuid import uuid4
from asyncio import CancelledError
from copy import deepcopy
from .models import (CallContext, DispatchInput, DispatchProposal, EtaLegRequest, EtaResult,
                     CallSuccess, CallFailure, ErrorInfo)
from .validation import DispatchError
from .eta_validation import validate_eta_evidence


async def decide_dispatch(context, payload, provider, query_eta, *, ensure_active, shared_resources=None):
    context = CallContext.model_validate(context)
    try:
        source = decode_dispatch_input(payload)
        ensure_active()
        if (context.run_id, context.patient_id) != (source.run_id, source.patient_id):
            raise DispatchError("DISPATCH_FAILED", "dispatch context/payload identity mismatch")
        queried_routes = []
        terminal_failure = None
        callback_open = True

        async def callback(request):
            nonlocal terminal_failure
            if not callback_open:
                raise DispatchError("DISPATCH_FAILED", "dispatch callback is closed")
            if terminal_failure is not None:
                raise terminal_failure
            try:
                ensure_active()
                request = EtaLegRequest.model_validate(EtaLegRequest.model_validate(request).model_dump())
                # Reserve the query order before awaiting, even for concurrent callers.
                index = len(queried_routes)
                queried_routes.append(None)
                child = CallContext(call_id=uuid4().hex, run_id=context.run_id, patient_id=context.patient_id)
                response = await query_eta(child, EtaLegRequest.model_validate(request.model_dump()))
                result = EtaResult.model_validate(EtaResult.model_validate(response).model_dump())
                ensure_active()
                if result.status == "failed":
                    raise DispatchError("ETA_FAILED", "ETA query failed")
                queried_routes[index] = (request, result)
                return EtaResult.model_validate(result.model_dump())
            except CancelledError as exc:
                terminal_failure = terminal_failure if terminal_failure is not None else exc
                raise
            except Exception as exc:
                # External details (including failed.detail) must never enter summaries.
                if isinstance(exc, DispatchError):
                    code = exc.code
                elif isinstance(exc, TimeoutError):
                    code = "ETA_TIMEOUT"
                else:
                    code = "ETA_FAILED"
                messages = {"ETA_FAILED": "ETA query failed or returned invalid data",
                            "ETA_TIMEOUT": "ETA query timed out",
                            "RESOURCE_UNAVAILABLE": "ETA resource or run is unavailable",
                            "DISPATCH_FAILED": "dispatch is no longer active or valid"}
                if code not in messages:
                    code = "ETA_FAILED"
                failure = DispatchError(code, messages[code])
                terminal_failure = terminal_failure if terminal_failure is not None else failure
                raise failure from None

        # Own a new model tree so a provider cannot mutate the backend's plan/resources.
        try:
            if shared_resources is None:
                proposal = await provider.decide_dispatch(decode_dispatch_input(source), callback)
            else:
                # Explicit opt-in; never silently call an old provider which cannot
                # receive the shared snapshot. It receives data, not a manager.
                method = getattr(provider, 'decide_dispatch_with_resources', None)
                if method is None:
                    raise DispatchError('DISPATCH_FAILED', 'provider does not support shared resource input')
                proposal = await method(decode_dispatch_input(source), callback,
                                        deepcopy(shared_resources))
        except DispatchError as exc:
            code = exc.code if exc.code in {"DISPATCH_FAILED", "RESOURCE_UNAVAILABLE", "ETA_FAILED", "ETA_TIMEOUT"} else "DISPATCH_FAILED"
            raise DispatchError(code, "dispatch provider failed") from None
        finally:
            callback_open = False
            # A provider catching a callback exception cannot restore a failed invocation.
            if terminal_failure is not None:
                raise terminal_failure
        ensure_active()
        proposal = DispatchProposal.model_validate(proposal.model_dump() if hasattr(proposal, "model_dump") else proposal)
        if proposal.patient_id != source.patient_id:
            raise DispatchError("DISPATCH_FAILED", "proposal patient identity mismatch")
        if any(record is None for record in queried_routes):
            raise DispatchError("DISPATCH_FAILED", "ETA query is still pending")
        validate_eta_evidence(source, proposal, queried_routes)
        return CallSuccess[DispatchProposal](call_id=context.call_id, data=proposal)
    except DispatchError as exc:
        return CallFailure(call_id=context.call_id, error=ErrorInfo(code=exc.code, message=str(exc),
                                                                   request_id=None, run_id=context.run_id, patient_id=context.patient_id))
    except Exception:
        # Never propagate SDK request/credentials or arbitrary provider text into a summary.
        return CallFailure(call_id=context.call_id, error=ErrorInfo(code="DISPATCH_FAILED", message="dispatch provider failed or returned invalid data",
                                                                   request_id=None, run_id=context.run_id, patient_id=context.patient_id))


async def query_eta_call(context, payload, adapter):
    """Optional INT03-ETA envelope around the data-level callback adapter."""
    context = CallContext.model_validate(context)
    try:
        result = await adapter.query_eta(context, payload)
        return CallSuccess[EtaResult](call_id=context.call_id, data=result)
    except DispatchError as exc:
        return CallFailure(call_id=context.call_id, error=ErrorInfo(code=exc.code, message=str(exc),
                          request_id=None, run_id=context.run_id, patient_id=context.patient_id))
    except Exception:
        return CallFailure(call_id=context.call_id, error=ErrorInfo(code="ETA_FAILED", message="invalid ETA request or provider failure",
                          request_id=None, run_id=context.run_id, patient_id=context.patient_id))
