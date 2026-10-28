import os

import pytest

from core301.agent import llm_provider
from core301.agent.manual_provider import ManualTreatmentProvider
from core301.contracts.context import AgentCaseContext
from core301.fixtures.resource_state import fixed_resources
from core301.pulse.observation_projector import ObservationProjector


@pytest.fixture
def env_root(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(llm_provider, "PROJECT_ROOT", root)
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        # Track initially absent keys too, so dotenv additions are undone after each test.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    return root


def test_dotenv_configuration_from_other_directory(env_root, tmp_path, monkeypatch):
    (env_root / ".env").write_text(
        "OPENAI_BASE_URL=https://example.com/v1\nOPENAI_API_KEY=test-only-key\nOPENAI_MODEL=test-model\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("OPENAI_MODEL=wrong-directory\n")
    monkeypatch.chdir(elsewhere)
    provider = llm_provider.LLMTreatmentProvider()
    assert provider._base_url == "https://example.com/v1"
    assert provider._api_key == "test-only-key"
    assert provider._model == "test-model"


def test_shell_environment_takes_precedence(env_root, monkeypatch):
    names = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL")
    (env_root / ".env").write_text("\n".join(f"{name}=file-value" for name in names))
    for name in names:
        monkeypatch.setenv(name, "shell-value")
    provider = llm_provider.LLMTreatmentProvider()
    assert (provider._base_url, provider._api_key, provider._model) == ("shell-value",) * 3


@pytest.mark.parametrize("file_exists", [False, True])
def test_missing_configuration_keeps_existing_error(env_root, file_exists):
    if file_exists:
        (env_root / ".env").write_text(
            "OPENAI_BASE_URL=\nOPENAI_API_KEY=test-only-key\nOPENAI_MODEL=\n")
    with pytest.raises(llm_provider.LLMConfigurationError) as exc:
        llm_provider.LLMTreatmentProvider()
    assert "OPENAI_BASE_URL" in str(exc.value)
    assert "OPENAI_MODEL" in str(exc.value)
    assert "test-only-key" not in str(exc.value)


def test_manual_does_not_load_dotenv(env_root):
    (env_root / ".env").write_text("OPENAI_MODEL=should-not-be-loaded\n")
    context = AgentCaseContext(patient_id="P", known_injuries=[],
                               patient_observation=ObservationProjector().project("P", 0, {}),
                               available_resources=fixed_resources())
    plan = {"patient_id": "P", "actions": []}
    assert ManualTreatmentProvider(plan).create_plan(context).model_dump() == plan
    assert "OPENAI_MODEL" not in os.environ
