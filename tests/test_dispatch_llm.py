import asyncio
import json
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import httpx
import openai
import pytest

from core301.dispatch import providers
from core301.dispatch.clock import SimulationClock
from core301.dispatch.demo import demo_input, demo_eta
from core301.dispatch.eta import EtaAdapter, FakeEtaProvider
from core301.dispatch.manager import ResourceManager
from core301.dispatch.models import DispatchProposal, CallFailure, CallContext
from core301.dispatch.service import decide_dispatch, query_eta_call
from test_dispatch import proposal, context, leg


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "PROJECT_ROOT", tmp_path)
    for key, value in {"OPENAI_BASE_URL": "https://mock.invalid/v1", "OPENAI_API_KEY": "test-only-secret",
                       "OPENAI_MODEL": "mock-dispatch"}.items():
        monkeypatch.setenv(key, value)
    state = {"messages": [{"role": "assistant", "content": json.dumps(proposal().model_dump())}],
             "requests": [], "options": [], "status": 200}
    def respond(request):
        state["requests"].append(json.loads(request.content))
        if state["status"] != 200:
            return httpx.Response(state["status"], json={"error": {"message": "test-only-secret must not be logged"}})
        message = state["messages"].pop(0)
        return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 0, "model": "mock-dispatch",
                                        "choices": [{"index": 0, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                                                     "message": message}]})
    def client(**kwargs):
        state["options"].append(kwargs)
        return openai.AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(providers, "AsyncOpenAI", client)
    return state


def tool_call(request, *, name="query_eta", call_id="tool-001"):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(request)}}]}


def run(api, *, tools=False, eta_provider=None, max_rounds=4):
    async def execute():
        source = demo_input()
        manager = ResourceManager(source, SimulationClock(45))
        eta = EtaAdapter(manager.snapshot, eta_provider or demo_eta(), manager.ensure_active)
        provider = providers.LLMDispatchProvider(enable_eta_tools=tools, max_tool_rounds=max_rounds)
        response = await decide_dispatch(context(), source, provider, eta.query_eta, ensure_active=manager.ensure_active)
        return response, eta, manager, source
    return asyncio.run(execute())


def test_exact_payload_no_context_severity_or_evaluation_and_no_retries(api):
    response, eta, manager, source = run(api)
    assert isinstance(response, CallFailure) and response.error.code == "DISPATCH_FAILED"
    assert eta.records == [] and manager.snapshot() == source
    request, = api["requests"]
    assert set(request) == {"model", "messages"}
    payload = json.loads(request["messages"][1]["content"])
    assert payload == source.model_dump()
    for forbidden in ("call_id", "context", "severity", "TreatmentEvaluation", "counterfactual_observation", "known_injuries", "treatment_priority", "evacuation_priority"):
        assert forbidden not in request["messages"][1]["content"]
    assert api["options"][0]["max_retries"] == 0 and api["options"][0]["timeout"] == 60.0
    assert source.treatment_plan.model_dump() == payload["treatment_plan"]


def test_minimal_eta_tool_roundtrip_uses_backend_query_id(api):
    source = demo_input()
    request = leg(source, leg="team_to_patient", resource_id="TEAM-001", origin=source.medical_teams[0].position).model_dump()
    api["messages"] = [{"role": "assistant", "content": json.dumps(proposal("team_response").model_dump())}]
    api["messages"].insert(0, tool_call(request))
    response, eta, _, _ = run(api, tools=True)
    assert response.data == proposal("team_response") and len(eta.records) == 1
    assert len(api["requests"]) == 2
    tool = api["requests"][0]["tools"][0]
    assert tool["function"]["name"] == "query_eta"
    assert set(tool["function"]["parameters"]["properties"]) == set(request)
    messages = api["requests"][1]["messages"]
    assert messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == "tool-001"
    assert json.loads(messages[-1]["content"]) == eta.records[0]["result"]
    assert eta.records[0]["context"]["call_id"] != context().call_id
    assert context().call_id not in json.dumps(api["requests"])


@pytest.mark.parametrize("content", [None, "", "not JSON", "```json\n{}\n```",
    json.dumps({**proposal().model_dump(), "task_id": "invented"}),
    json.dumps({**proposal().model_dump(), "patient_id": "other"}),
    json.dumps({**proposal().model_dump(), "treatment_plan": {"patient_id": "P-001", "actions": []}}),
    json.dumps({**proposal().model_dump(), "treatment_priority": 1}),
])
def test_invalid_llm_output_fails_without_repair_or_fallback(api, content):
    api["messages"] = [{"role": "assistant", "content": content}]
    response, eta, manager, source = run(api)
    assert isinstance(response, CallFailure) and response.error.code == "DISPATCH_FAILED"
    assert len(api["requests"]) == 1 and eta.records == [] and manager.snapshot() == source
    assert set(response.model_dump()) == {"call_id", "error"}


@pytest.mark.parametrize("name,extra", [("invent_resource", {}), ("query_eta", {"query_id": "guessed"}),
    ("query_eta", {"run_id": "other"}), ("query_eta", {"severity": 0.8})])
def test_invalid_tool_name_and_arguments_are_rejected(api, name, extra):
    api["messages"].insert(0, tool_call({**leg(demo_input()).model_dump(), **extra}, name=name))
    response, eta, _, _ = run(api, tools=True)
    assert isinstance(response, CallFailure) and response.error.code == "DISPATCH_FAILED"
    assert eta.records == [] and len(api["requests"]) == 1


def test_tool_opt_in_and_bounded_rounds(api):
    request = leg(demo_input()).model_dump()
    api["messages"] = [tool_call(request)]
    assert isinstance(run(api)[0], CallFailure)
    api["messages"] = [tool_call(request), tool_call(request, call_id="tool-002")]
    response, eta, _, _ = run(api, tools=True, max_rounds=1)
    assert isinstance(response, CallFailure) and len(eta.records) == 1


def test_selected_unreachable_route_is_rejected_even_if_llm_ignores_it(api):
    api["messages"].insert(0, tool_call(leg(demo_input()).model_dump()))
    eta = FakeEtaProvider({("ambulance_to_patient", "AMB-001", 10, 0, 20): ("unreachable", None, "closed")})
    response, _, manager, source = run(api, tools=True, eta_provider=eta)
    assert isinstance(response, CallFailure) and response.error.code == "RESOURCE_UNAVAILABLE"
    assert manager.snapshot() == source


def test_api_error_sanitized_and_not_retried(api):
    api["status"] = 503
    response, _, _, _ = run(api)
    assert response.error.code == "DISPATCH_FAILED"
    assert "test-only-secret" not in response.model_dump_json()
    assert len(api["requests"]) == 1


def test_prompt_packaged_and_loaded_relative_to_python_file(monkeypatch, tmp_path):
    path = Path(providers.__file__).resolve()
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("core301.dispatch._prompt_probe", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    assert loaded.SYSTEM_PROMPT == (path.parent / "prompts/dispatch_decision.md").read_text()
    root = path.parents[3]
    assert '"dispatch/prompts/*.md"' in (root / "pyproject.toml").read_text()


def test_llm_config_reuses_dotenv_and_shell_precedence(monkeypatch, tmp_path):
    from core301.agent.llm_config import LLMConfigurationError
    monkeypatch.setattr(providers, "PROJECT_ROOT", tmp_path)
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    (tmp_path / ".env").write_text("OPENAI_BASE_URL=https://mock.invalid/v1\nOPENAI_API_KEY=test-only-secret\nOPENAI_MODEL=file-model\n")
    monkeypatch.setenv("OPENAI_MODEL", "shell-model")
    monkeypatch.chdir(tmp_path.parent)
    provider = providers.LLMDispatchProvider()
    assert provider._config.model == "shell-model"
    assert "test-only-secret" not in repr(provider._config)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        providers.LLMDispatchProvider()


def test_eta_envelope_returns_exact_success_or_error():
    async def execute():
        source = demo_input()
        manager = ResourceManager(source, SimulationClock(45))
        eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
        reply = await query_eta_call(context(), leg(source), eta)
        assert set(reply.model_dump()) == {"call_id", "data"} and reply.call_id == context().call_id
        error = await query_eta_call(context("other"), {**leg(source).model_dump(), "query_id": "forged"}, eta)
        assert set(error.model_dump()) == {"call_id", "error"} and error.error.request_id is None
    asyncio.run(execute())


def test_llm_evacuation_requires_complete_tool_evidence(api):
    from test_dispatch_eta_evidence import routes
    first, second = routes()
    api["messages"] = [tool_call(first.model_dump()), tool_call(second.model_dump(), call_id="tool-002"),
                       {"role": "assistant", "content": json.dumps(proposal().model_dump())}]
    response, eta, manager, source = run(api, tools=True)
    assert response.data == proposal()
    assert len(eta.records) == 2 and len(api["requests"]) == 3
    assert manager.snapshot() == source
