import json
import sys
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from core301 import cli
from core301.agent import llm_provider
from core301.paths import PROJECT_ROOT


@pytest.mark.parametrize("explicit", [False, True])
def test_llm_patient_file_batch(monkeypatch, tmp_path, explicit):
    cases = json.loads((PROJECT_ROOT / "src/core301/fixtures/casualties_v1.json").read_text())
    # A separate project path proves the CLI reads this file, not the old package fixture.
    (tmp_path / "patient-test").mkdir()
    cases[0]["patient_id"] = "file-selected-patient"
    path = tmp_path / "patient-test/casualties_v1.json"
    path.write_text(json.dumps(cases))
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    provider = Mock()
    factory = Mock(return_value=provider)
    runtime = Mock()
    runtime_factory = Mock(return_value=runtime)
    monkeypatch.setattr(llm_provider, "LLMTreatmentProvider", factory)
    monkeypatch.setattr(cli, "CaseRuntime", runtime_factory)
    monkeypatch.chdir(tmp_path.parent)
    args = ["core301", "--provider", "llm"]
    if explicit:
        args += ["--casualty", str(path)]
    monkeypatch.setattr(sys, "argv", args)
    cli.main()
    assert [c.args[0] for c in runtime_factory.call_args_list] == [c["patient_id"] for c in cases]
    assert [c.args[0] for c in runtime.run_once.call_args_list] == cases
    assert all(c.kwargs["provider"] is provider for c in runtime.run_once.call_args_list)


def test_invalid_batch_rejected_before_api_or_pulse(monkeypatch, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"patient_id": "P", "injuries": []}, {"patient_id": "invalid"}]))
    provider_factory, runtime_factory = Mock(), Mock()
    monkeypatch.setattr(llm_provider, "LLMTreatmentProvider", provider_factory)
    monkeypatch.setattr(cli, "CaseRuntime", runtime_factory)
    monkeypatch.setattr(sys, "argv", ["core301", "--provider", "llm", "--casualty", str(path)])
    with pytest.raises(ValidationError):
        cli.main()
    provider_factory.assert_not_called()
    runtime_factory.assert_not_called()
