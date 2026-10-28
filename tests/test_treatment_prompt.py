from pathlib import Path
import re
import runpy

from core301.agent import llm_provider
from core301.contracts.casualty import TEMPLATES
from core301.contracts.treatment import ACTION_TYPES


def test_prompt_loaded_from_package_with_different_working_directory(monkeypatch, tmp_path):
    provider_path = Path(llm_provider.__file__).resolve()
    expected = (provider_path.parent / "prompts/treatment_decision.md").read_text(encoding="utf-8")
    # Read the module afresh after changing cwd; do not merely check a cached import.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/treatment_decision.md").write_text("wrong working directory prompt")
    loaded = runpy.run_path(str(provider_path))
    assert loaded["SYSTEM_PROMPT"] == expected
    assert llm_provider.SYSTEM_PROMPT == expected


def test_prompt_covers_frozen_injuries_and_actions():
    prompt = llm_provider.SYSTEM_PROMPT
    # The capability section must cover all ten injuries, not just mention them elsewhere.
    injury_sections = re.findall(r"^\d+\. ([a-z_]+)$", prompt, flags=re.MULTILINE)
    assert len(injury_sections) == 10
    assert set(injury_sections) == set(TEMPLATES)
    # The output allowlist must remain exactly the eight Frozen treatment branches.
    action_fields = re.findall(r"^- ([a-z_]+)：action_type(?:、side)?$", prompt, flags=re.MULTILINE)
    assert len(action_fields) == 8
    assert set(action_fields) == set(ACTION_TYPES)
