"""Read-only current research-file, locked-rule, and source import checks. No native experiments."""
from pathlib import Path
import hashlib,json,sys,importlib.util
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from core301.paths import PROJECT_ROOT
assert PROJECT_ROOT==ROOT
manifest=json.loads((ROOT/'research_baseline/CURRENT_RESEARCH_FILES.json').read_text())
errors=[]
for name,record in manifest.items():
    p=ROOT/name
    expected=record.get('target_sha256',record['source_sha256'])
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:errors.append(name)
C=ROOT/'research_artifacts/treatment_effect_rules_v2_candidate_v0.1'
lock=json.loads((C/'treatment_effect_rules_v1_final/RULE_VERSION_MANIFEST.json').read_text())
rules=C/'treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json'
assert hashlib.sha256(rules.read_bytes()).hexdigest()==lock['rules_sha256']
sys.path.insert(0,str(C/'male_independent_validation_final_preparation_v1'))
import adapter,common
cfg=common.config();common.calc.validate(cfg)
assert len(cfg['rules'])==14
assert common.digest(cfg['parameter_registry'])==lock['parameter_registry_canonical_sha256']
assert common.digest({r['rule_id']:r['definitions'] for r in cfg['rules']})==lock['definitions_canonical_sha256']
for mod in [adapter,common,common.calc,common.calc.old]:
    assert Path(mod.__file__).resolve().is_relative_to(ROOT)
assert not errors,errors
print(json.dumps({'current_research_files_checked':len(manifest),'errors':errors,'locked_rule_count':len(cfg['rules']),'rules_sha256':lock['rules_sha256'],'evaluator':str(Path(adapter.__file__).relative_to(ROOT)),'project_root':str(PROJECT_ROOT)},indent=2))
