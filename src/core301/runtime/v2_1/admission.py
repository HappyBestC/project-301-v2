"""Pinned composite engineering admission; no inherited risk exemptions."""
import hashlib,json
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
ADMITTED={'penetrating_thoracic_composite_v2': '301.v2_1.thoracic.aligned_onsets.2', 'blunt_thoracoabdominal_composite_v2': '301.v2_1.composite.candidate.1', 'blast_hemorrhage_respiratory_composite_v2': '301.v2_1.composite.candidate.1', 'fire_co_alveolar_composite_v2': '301.v2_1.composite.candidate.1', 'trapped_hypoxia_dehydration_composite_v2': '301.v2_1.composite.candidate.1'}
MANIFEST=PROJECT_ROOT/'research_artifacts/v2_1_battle_composite_injuries_v0.1/validation/admission_v2.json'
MANIFEST_SHA256='cd1ca04cac21bd0a195a083186c34058fbc8316c418bcd20b010aa288039b441'
def verify_admission(pattern_id):
 if pattern_id not in ADMITTED:raise V2Error('ADMISSION_PENDING','Composite evidence/safety/regression not yet approved')
 if not MANIFEST.is_file() or hashlib.sha256(MANIFEST.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise V2Error('ADMISSION_EVIDENCE_INVALID','Admission manifest missing/changed')
 m=json.loads(MANIFEST.read_text())
 for relative,digest in m['proof_sha256'].items():
  p=PROJECT_ROOT/relative
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise V2Error('ADMISSION_EVIDENCE_INVALID','Pinned engineering proof changed: '+relative)
 if m['admitted'][pattern_id]['production_enabled'] is not False:raise V2Error('PRODUCTION_NOT_ENABLED','Invalid production permission')
 return ADMITTED[pattern_id]
