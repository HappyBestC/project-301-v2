import json
from pathlib import Path
import pytest
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2 import open_research_case

@pytest.mark.parametrize('kind',['hemothorax','carbon_monoxide_exposure','environmental_hypoxia'])
def test_admission_has_pinned_completed_evidence(kind):
    from core301.runtime.v2.restricted_admission import verify_admission
    from core301.runtime.v2.restricted_registry import REGISTRY
    assert verify_admission(kind)==REGISTRY[kind].profile
    assert REGISTRY[kind].admission=='ADMITTED_RESTRICTED' and not REGISTRY[kind].production_enabled

def test_manifest_tamper_fails_before_case_files(tmp_path,monkeypatch):
    import core301.runtime.v2.restricted_admission as admission
    bad=tmp_path/'tampered.json';bad.write_text('{}')
    monkeypatch.setattr(admission,'MANIFEST_PATH',str(bad))
    p=tmp_path/'never'
    with pytest.raises(V2Error) as e:open_research_case('environmental_hypoxia',patient_id='P',run_id='R',directory=p,mode='research')
    assert e.value.code=='ADMISSION_EVIDENCE_INVALID' and not p.exists()

def test_missing_completed_evidence_denied(tmp_path,monkeypatch):
    import core301.runtime.v2.restricted_admission as admission
    original=admission.PROJECT_ROOT/admission.MANIFEST_PATH
    copied=tmp_path/admission.MANIFEST_PATH;copied.parent.mkdir(parents=True);copied.write_bytes(original.read_bytes())
    monkeypatch.setattr(admission,'PROJECT_ROOT',tmp_path)
    with pytest.raises(V2Error) as e:admission.verify_admission('hemothorax')
    assert e.value.code=='ADMISSION_EVIDENCE_INVALID'

def test_agent_cannot_supply_admission_flag(tmp_path):
    p=tmp_path/'never'
    with pytest.raises(TypeError):open_research_case('hemothorax',patient_id='P',run_id='R',directory=p,mode='research',admitted=True)
    assert not p.exists()
