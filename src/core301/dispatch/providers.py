from .complete_contracts import decode_dispatch_input
import json
from pathlib import Path
from typing import Protocol
from openai import AsyncOpenAI
from core301.agent.llm_config import load_llm_config
from core301.paths import PROJECT_ROOT
from .eta import QueryEta
from .models import DispatchInput, DispatchProposal, EtaLegRequest
from .validation import DispatchError

SYSTEM_PROMPT = (Path(__file__).parent / "prompts/dispatch_decision.md").read_text(encoding="utf-8")
SHARED_RESOURCE_INSTRUCTIONS = (Path(__file__).parent / "prompts/shared_resources.md").read_text(encoding="utf-8")


class DispatchProvider(Protocol):
    async def decide_dispatch(self, dispatch_input: DispatchInput, query_eta: QueryEta) -> DispatchProposal: ...


class FixedDispatchProvider:
    """Explicit demo selection, not a medical or minimum-travel-time scheduling policy."""
    def __init__(self, proposal):
        self.proposal = DispatchProposal.model_validate(proposal)

    async def decide_dispatch_with_resources(self, dispatch_input, query_eta, shared_resources):
        # Fixed fixture intentionally may propose unavailable resources so the
        # deterministic backend rejection path remains testable.
        return await self.decide_dispatch(dispatch_input, query_eta)

    async def decide_dispatch(self, dispatch_input, query_eta):
        source = decode_dispatch_input(dispatch_input)
        proposal = DispatchProposal.model_validate(self.proposal.model_dump())
        if proposal.patient_id != source.patient_id:
            raise DispatchError("DISPATCH_FAILED", "fixed proposal patient mismatch")
        departure = source.patient_observation.simulation_time_s
        if proposal.mode == "onsite":
            return proposal
        team = proposal.mode == "team_response"
        resources = source.medical_teams if team else source.ambulances
        key, value = ("team_id", proposal.team_id) if team else ("ambulance_id", proposal.ambulance_id)
        resource = next((r for r in resources if getattr(r, key) == value), None)
        if resource is None:
            raise DispatchError("DISPATCH_FAILED", "fixed selection resource is absent")
        result = await query_eta(EtaLegRequest(leg="team_to_patient" if team else "ambulance_to_patient",
                                              resource_id=value, origin=resource.position, destination=source.position,
                                              departure_at_s=departure))
        if result.status != "available":
            raise DispatchError("RESOURCE_UNAVAILABLE", "fixed candidate cannot reach patient")
        if not team:
            facility = next((f for f in source.facilities if f.facility_id == proposal.target_facility_id), None)
            if facility is None:
                raise DispatchError("DISPATCH_FAILED", "fixed target facility is absent")
            result = await query_eta(EtaLegRequest(leg="patient_to_facility", resource_id=value,
                                                  origin=source.position, destination=facility.position,
                                                  departure_at_s=departure + result.travel_duration_s))
            if result.status != "available":
                raise DispatchError("RESOURCE_UNAVAILABLE", "fixed candidate cannot reach facility")
        return proposal


class LLMDispatchProvider:
    async def decide_resource_schedule(self, dispatch_input, **options):
        """Document-based batch schedule; separate from the legacy MR5 contract."""
        from .minimal.api import request_agent_schedule
        return await request_agent_schedule(self, dispatch_input, **options)

    def __init__(self, *, enable_eta_tools=False, max_tool_rounds=4):
        if type(max_tool_rounds) is not int or max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be a positive integer")
        self._config = load_llm_config(PROJECT_ROOT)
        self.enable_eta_tools, self.max_tool_rounds = enable_eta_tools, max_tool_rounds

    async def decide_dispatch(self, dispatch_input, query_eta):
        payload = decode_dispatch_input(dispatch_input).model_dump()
        return await self._decide(payload, query_eta)

    async def decide_dispatch_with_resources(self, dispatch_input, query_eta, shared_resources):
        payload = decode_dispatch_input(dispatch_input).model_dump()
        payload['shared_resources'] = shared_resources
        return await self._decide(payload, query_eta)

    async def _decide(self, payload, query_eta):
        prompt = SYSTEM_PROMPT
        if "shared_resources" in payload:
            prompt += "\n\n" + SHARED_RESOURCE_INSTRUCTIONS
        if payload.get("schema_version") == "301.dispatch.complete.1":
            prompt += "\n\n" + (Path(__file__).parent / "prompts/complete_plan.md").read_text(encoding="utf-8")
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]
        tool = {"type": "function", "function": {"name": "query_eta", "description": "查询一个候选行程的仿真时长；仅预测，不确认到达。",
                                                  "parameters": EtaLegRequest.model_json_schema()}}
        config = self._config
        seen_calls = set()
        async with AsyncOpenAI(base_url=config.base_url, api_key=config.api_key, max_retries=0, timeout=60.0) as client:
            for turn in range(self.max_tool_rounds + 1):
                options = {"tools": [tool], "tool_choice": "auto"} if self.enable_eta_tools else {}
                response = await client.chat.completions.create(model=config.model, messages=messages, **options)
                if not response.choices:
                    raise DispatchError("DISPATCH_FAILED", "dispatch LLM returned no choices")
                message = response.choices[0].message
                if message.tool_calls:
                    if not self.enable_eta_tools or turn >= self.max_tool_rounds:
                        raise DispatchError("DISPATCH_FAILED", "unexpected tool call or ETA tool-round limit reached")
                    if message.content and message.content.strip():
                        raise DispatchError("DISPATCH_FAILED", "tool response must not also contain a proposal")
                    messages.append({"role": "assistant", "content": None,
                                     "tool_calls": [call.model_dump(exclude_none=True) for call in message.tool_calls]})
                    for call in message.tool_calls:
                        if call.type != "function" or call.function.name != "query_eta" or call.id in seen_calls:
                            raise DispatchError("DISPATCH_FAILED", "unknown or duplicate dispatch tool call")
                        seen_calls.add(call.id)
                        request = EtaLegRequest.model_validate(json.loads(call.function.arguments))
                        result = await query_eta(request)
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": result.model_dump_json()})
                    continue
                if not isinstance(message.content, str) or not message.content.strip():
                    raise DispatchError("DISPATCH_FAILED", "dispatch LLM returned no JSON content")
                proposal = DispatchProposal.model_validate(json.loads(message.content))
                if proposal.patient_id != payload["patient_id"]:
                    raise DispatchError("DISPATCH_FAILED", "dispatch LLM changed patient identity")
                return proposal
        raise DispatchError("DISPATCH_FAILED", "dispatch did not produce a proposal")
