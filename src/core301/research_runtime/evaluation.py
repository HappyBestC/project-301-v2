"""Invoke the unchanged manifest evaluator; preserve refusal, never invent grades."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from core301.paths import PROJECT_ROOT

RULE_ROOT = PROJECT_ROOT/'research_artifacts/treatment_effect_rules_v2_candidate_v0.1'
RULE_SHA = '6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f'
PARAM_SHA = 'ed3ed8ae24f4da9f887202318c372f60a39ff95d3b9ffecf91b7870819c090f7'
DEF_SHA = '634a7a9abd54dac6643a9dd61303b80160fbc1bd7236fb691d802ef1f1aa3de2'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def verify_rules():
    path = RULE_ROOT/'final_rule_calibration_v1/FINAL_RULE_TABLE.json'
    if sha(path)!=RULE_SHA or sha(RULE_ROOT/'treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json')!=RULE_SHA:
        raise ValueError('Locked rules changed')
    cfg = json.loads(path.read_text())
    if canonical(cfg['parameter_registry'])!=PARAM_SHA or canonical({r['rule_id']:r['definitions'] for r in cfg['rules']})!=DEF_SHA:
        raise ValueError('Locked canonical parameters/definitions changed')
    return cfg


def source(path):
    path=Path(path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError('Evaluation evidence must be inside this research project')
    return {'path':str(path.relative_to(PROJECT_ROOT)), 'sha256':sha(path)}


def evaluate(directory, plan, simulation_time_s):
    verify_rules()
    # Actual StandardMale evidence, intentionally NOT substituted with the
    # independent matrix's Soldier input. No control branch is fabricated.
    manifest={
        'rule_id':'V2E-01', 'rule_snapshot_sha256':RULE_SHA,
        'run_id':plan.run_id, 'patient_id':plan.patient_id,
        'plan_id':plan.plan_id, 'action_instance_ids':[a.action_instance_id for a in plan.actions],
        'data_kind':'AUTHORIZED_NATIVE', 'research_read_authorized':True,
        'dataset_id':plan.run_id, 'experiment_id':'external_s0.4_zero',
        'control_experiment_id':'external_s0.4_Control',
        'injury_type':plan.scope_id, 'profile':'301.v2.phase1.research.1',
        'severity':plan.severity, 'injury_location':{'compartment':'RightLeg'},
        'action_time_s':180, 'evaluation_end_s':480, 'engine_version':'4.3.2',
        'patient_source':source(directory/'patient_input.json'),
        'treatment':{'events':source(directory/'native_events.json'),
                     'observations':source(directory/'observations.jsonl'),
                     'actions':source(directory/'execution_events.jsonl'),
                     'initial_state':source(directory/'patient_initial_state.json'),
                     'pretreatment_state':source(directory/'pretreatment_state.json'),
                     'final_state':source(directory/'final_state.json')},
        'control':None,
        'evidence_gaps':['NO_MATCHED_CONTROL_BRANCH', 'STANDARDMALE_NOT_INDEPENDENT_SOLDIER_INPUT',
                         'NO_INDEPENDENT_EXECUTION_EVIDENCE_CONTRACT',
                         'HOST_OBSERVATION_EXPORT_NOT_INDEPENDENT_ADAPTER_BRANCH_SCHEMA'],
    }
    path=directory/'evaluation_manifest.json'
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    adapter=RULE_ROOT/'male_independent_validation_final_preparation_v1/adapter.py'
    command=[sys.executable,'-B',str(adapter),str(path)]
    result=subprocess.run(command,cwd=PROJECT_ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},
                          capture_output=True,text=True,timeout=60)
    (directory/'evaluator_stdout.json').write_text(result.stdout)
    (directory/'evaluator_stderr.log').write_text(result.stderr)
    call={'command':command,'returncode':result.returncode,'adapter_sha256':sha(adapter),
          'manifest_sha256':sha(path),'simulation_time_s':simulation_time_s}
    (directory/'evaluation_call.json').write_text(json.dumps(call,indent=2)+'\n')
    if result.returncode:
        raise RuntimeError('Locked evaluator process failed; see evaluator_stderr.log')
    raw=json.loads(result.stdout)
    # This runner cannot authorize a formal grade even if future dependencies change.
    if raw['computation_state']!='NOT_EVALUABLE' or raw['formal_grade'] is not None:
        raise RuntimeError('Incomplete evidence unexpectedly scored')
    return {'run_id':plan.run_id,'patient_id':plan.patient_id,'plan_id':plan.plan_id,
            'action_instance_ids':[a.action_instance_id for a in plan.actions],
            'rule_version':'RESEARCH_RULESET_V1_LOCKED','rule_id':'V2E-01','rule_sha256':RULE_SHA,
            'scope':'external_hemorrhage RightLeg .4 / StandardMale / 180-480s',
            'evaluator_called':True,'evaluator_entry':str(adapter.relative_to(PROJECT_ROOT))+':evaluate',
            'computation_state':raw['computation_state'],'grade':None,
            'minimum':raw.get('subconditions',{}).get('minimum'),
            'complete':raw.get('subconditions',{}).get('complete'),
            'evidence_gaps':manifest['evidence_gaps'],'raw_evaluator_result':raw,
            'evidence_manifest':source(path),'formal_scoring_enabled':False}
