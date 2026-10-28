"""Exercise the real locked entry, not a replacement scorer."""
import json
import os
import subprocess
import sys
import pytest
from core301.research_runtime.evaluation import RULE_ROOT,verify_rules


@pytest.mark.parametrize('manifest',[
    {'rule_id':'V2E-01'},
    {'rule_id':'V2E-01','data_kind':'SYNTHETIC_TEST_ONLY','research_read_authorized':False,
     'rule_snapshot_sha256':'incorrect','treatment':{}}
])
def test_real_locked_entry_refuses_missing_or_invalid_evidence(tmp_path,manifest):
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    adapter=RULE_ROOT/'male_independent_validation_final_preparation_v1/adapter.py'
    proc=subprocess.run([sys.executable,'-B',str(adapter),str(path)],capture_output=True,text=True,
                        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=30)
    assert proc.returncode==0,proc.stderr
    result=json.loads(proc.stdout)
    assert result['computation_state']=='NOT_EVALUABLE'
    assert result['formal_grade'] is None
    assert result['errors'] and result['subconditions']=={}
    verify_rules()
