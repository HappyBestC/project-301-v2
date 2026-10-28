import json
import sys
from unittest.mock import Mock

import httpx
import openai
import pytest
from pydantic import ValidationError

from core301 import cli
from core301.agent import llm_provider
from core301.agent.manual_provider import ManualTreatmentProvider
from core301.contracts.casualty import CasualtyInput
from core301.contracts.context import AgentCaseContext
from core301.contracts.observation import PatientObservation
from core301.context.builder import AgentCaseContextBuilder
from core301.fixtures.resource_state import fixed_resources
from core301.paths import PROJECT_ROOT
from core301.pulse.observation_projector import ObservationProjector
from core301.runtime.case_runtime import CaseRuntime


PLAN = {"patient_id": "patient_004", "actions": [{"action_type": "occlusive_dressing", "side": "Left"}]}
ENV = {"OPENAI_BASE_URL": "https://mock.invalid/v1", "OPENAI_API_KEY": "mock-only-not-a-credential",
       "OPENAI_MODEL": "mock-model"}


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Actual SDK serialization/parsing, entirely in-process mocked HTTP transport."""
    monkeypatch.setattr(llm_provider, "PROJECT_ROOT", tmp_path)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    state = {"content": json.dumps(PLAN), "status": 200, "requests": [], "options": []}

    def respond(request):
        state["requests"].append(request)
        body = {"id": "mock-completion", "object": "chat.completion", "created": 0, "model": "mock-model",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": state["content"]}}]}
        if state.get("empty_choices"):
            body["choices"] = []
        if state["status"] != 200:
            body = {"error": {"message": "mock service failure", "type": "server_error"}}
        return httpx.Response(state["status"], json=body)

    def client(**kwargs):
        state["options"].append(kwargs)
        return openai.OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(llm_provider, "OpenAI", client)
    return state


@pytest.fixture
def context():
    casualty = CasualtyInput.model_validate_json(
        (PROJECT_ROOT / "src/core301/fixtures/first_case.json").read_text())
    observation = ObservationProjector().project(casualty.patient_id, 0, {})
    return AgentCaseContextBuilder().build(casualty, observation, fixed_resources())


def test_whitelist_valid_plan_and_plain_chat_request(api, context):
    original = context.model_dump()
    plan = llm_provider.LLMTreatmentProvider().create_plan(context)
    assert plan.model_dump() == PLAN
    assert context.model_dump() == original
    request, = api["requests"]
    assert request.method == "POST" and str(request.url) == ENV["OPENAI_BASE_URL"] + "/chat/completions"
    body = json.loads(request.content)
    assert set(body) == {"model", "messages"}
    assert body["model"] == ENV["OPENAI_MODEL"]
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == (
        PROJECT_ROOT / "src/core301/agent/prompts/treatment_decision.md"
    ).read_text(encoding="utf-8")
    sent = json.loads(body["messages"][1]["content"])
    assert sent == {key: original[key] for key in ("patient_id", "known_injuries", "patient_observation")}
    for forbidden in ("severity", "available_resources", "ActiveActions", "run_summary", "BloodVolume", "debug"):
        assert forbidden not in body["messages"][1]["content"]
    assert api["options"][0]["max_retries"] == 0
    assert api["options"][0]["timeout"] == 60


@pytest.mark.parametrize("missing", ENV)
def test_missing_configuration(api, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(llm_provider.LLMConfigurationError, match=missing):
        llm_provider.LLMTreatmentProvider()
    assert not api["requests"]


def test_blank_configuration(api, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "  ")
    with pytest.raises(llm_provider.LLMConfigurationError, match="OPENAI_MODEL"):
        llm_provider.LLMTreatmentProvider()


@pytest.mark.parametrize("content", [None, "", " \n "])
def test_empty_response(api, context, content):
    api["content"] = content
    with pytest.raises(llm_provider.LLMEmptyResponseError):
        llm_provider.LLMTreatmentProvider().create_plan(context)


def test_empty_choices(api, context):
    api["empty_choices"] = True
    with pytest.raises(llm_provider.LLMEmptyResponseError):
        llm_provider.LLMTreatmentProvider().create_plan(context)


@pytest.mark.parametrize("content", ["not JSON", "```json\n" + json.dumps(PLAN) + "\n```"])
def test_invalid_json_is_not_repaired(api, context, content):
    api["content"] = content
    with pytest.raises(json.JSONDecodeError):
        llm_provider.LLMTreatmentProvider().create_plan(context)
    assert len(api["requests"]) == 1


@pytest.mark.parametrize("actions", [
    [{"action_type": "occlusive_dressing"}],
    [{"action_type": "tourniquet"}],
    [{"action_type": "transfusion", "Rate": 100}],
    [{"action_type": "mechanical_ventilation"}],
])
def test_invalid_plan_is_not_repaired(api, context, actions):
    api["content"] = json.dumps({"patient_id": context.patient_id, "actions": actions})
    with pytest.raises(ValidationError):
        llm_provider.LLMTreatmentProvider().create_plan(context)
    assert len(api["requests"]) == 1


def test_patient_mismatch(api, context):
    api["content"] = json.dumps({**PLAN, "patient_id": "different"})
    with pytest.raises(ValueError, match="patient_id"):
        llm_provider.LLMTreatmentProvider().create_plan(context)


def test_api_failure_no_retry_or_fallback(api, context):
    api["status"] = 503
    with pytest.raises(openai.APIStatusError) as exc:
        llm_provider.LLMTreatmentProvider().create_plan(context)
    assert exc.value.status_code == 503
    assert len(api["requests"]) == 1


def test_manual_still_works_without_api_config(monkeypatch, context):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    assert ManualTreatmentProvider(PLAN).create_plan(context).model_dump() == PLAN


def test_cli_default_is_manual(monkeypatch):
    runtime = Mock()
    monkeypatch.setattr(cli, "CaseRuntime", Mock(return_value=runtime))
    monkeypatch.setattr(sys, "argv", ["core301"])
    cli.main()
    args, kwargs = runtime.run_once.call_args
    assert args[1] == PLAN and kwargs["provider"] is None


def test_cli_llm_rejects_manual_plan(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["core301", "--provider", "llm", "--plan", "unused.json"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_runtime_records_llm_failure_without_treatment(api, tmp_path):
    from test_runtime import SessionStub
    api["content"] = "not JSON"
    session = SessionStub()
    runtime = CaseRuntime("P", tmp_path, session=session)
    with pytest.raises(json.JSONDecodeError):
        runtime.run_once({"patient_id": "P", "injuries": []}, provider=llm_provider.LLMTreatmentProvider())
    summary = json.loads((runtime.run_dir / "run_summary.json").read_text())
    assert summary["failed_phase"] == "plan" and summary["error_type"] == "JSONDecodeError"
    assert not session.action_results and session.closed
    assert not (runtime.run_dir / "observation_after.json").exists()


@pytest.mark.integration
def test_cli_mock_api_to_real_pulse(api, monkeypatch, tmp_path, capsys):
    # A mocked API response, never claimed as a real external-model smoke test.
    monkeypatch.setattr(sys, "argv", ["core301", "--provider", "llm", "--runs-dir", str(tmp_path),
                                     "--casualty", str(PROJECT_ROOT / "src/core301/fixtures/first_case.json")])
    cli.main()
    path, = tmp_path.iterdir()
    summary = json.loads((path / "run_summary.json").read_text())
    assert summary["status"] == "completed"
    assert summary["treatment_apply_result"][0]["accepted"]
    assert summary["simulation_time_s_after_treatment"] > summary["simulation_time_s_before_observation"]
    assert json.loads((path / "treatment_plan.json").read_text()) == PLAN
    PatientObservation.model_validate_json((path / "observation_after.json").read_text())
    AgentCaseContext.model_validate_json((path / "context.json").read_text())
    assert len(api["requests"]) == 1
    assert str(path) in capsys.readouterr().out
