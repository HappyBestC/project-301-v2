"""Pinned completed engineering evidence; never a clinical/user signature."""
import hashlib,json
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
MANIFEST_PATH='research_artifacts/v2_final_ten_injury_restricted_acceptance_v0.1/INTEGRATION/ADMISSION_MANIFEST.json'
MANIFEST_SHA256='ce6bc0e6dc1feab15fd87e18dc69566b2371c778340c84e96b2d16cfdb7e4871'
def verify_admission(kind):
    p=PROJECT_ROOT/MANIFEST_PATH
    try:
        if hashlib.sha256(p.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise ValueError('manifest hash')
        m=json.loads(p.read_text())
        if kind not in m['profiles'] or m['production_enabled'] is not False:raise ValueError('profile/mode')
        for e in m['evidence']:
            if hashlib.sha256((PROJECT_ROOT/e['path']).read_bytes()).hexdigest()!=e['sha256']:raise ValueError('evidence hash')
        return m['profiles'][kind]
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise V2Error('ADMISSION_EVIDENCE_INVALID','Completed engineering evidence missing or changed') from exc
