"""User-authorized fixed-profile risk, with fail-closed evidence conformance.

The numeric tolerance is the existing project's deterministic regression
precision, not a sodium/clinical safety range fitted to successful outcomes.
Any divergence requires review; no other patient's trajectory is accepted.
"""
import csv,hashlib,json,math
from functools import lru_cache
from pathlib import Path
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.exposure_validation import PUBLIC_FIELDS
RISK_ID='301.v2.limited_research_risk_acceptance.2026-10-13.1'
PRECISION=1e-7
FILES={'hemo': {'path': 'research_artifacts/v2_ten_injury_completion_program_v0.1/experiments/raw/hemo/combined/observations.csv', 'sha256': '19d3b2ded69cf4a8acaba818d605702e513dbbafe1f090439e890723ead70dc7'}, 'co_pre': {'path': 'research_artifacts/v2_ten_injury_completion_program_v0.1/experiments/raw/runtime_attempt2/carbon_monoxide_exposure/base/observations.jsonl', 'sha256': '482feeb1956cea55448a9a550d6adc5eddb1d98a691fe2da5b7e4a0d7ece06d0'}, 'co_post': {'path': 'research_artifacts/v2_ten_injury_completion_program_v0.1/experiments/raw/runtime_attempt2/carbon_monoxide_exposure/treated/observations.jsonl', 'sha256': '4ce191bb42b5a38b5dcacbb9d51a89972477b2f31495f783b78a0230c6de6f86'}, 'approval': {'path': 'research_artifacts/v2_final_ten_injury_restricted_acceptance_v0.1/USER_RISK_ACCEPTANCE.json', 'sha256': '651ccba0cb3baa8974fffa91ef5b7f5e70f88629578265d8a1819160249f9b09'}}

def verified_text(key):
    ref=FILES[key];p=PROJECT_ROOT/ref['path']
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=ref['sha256']:
        raise V2Error('RISK_EVIDENCE_MISMATCH','Pinned risk approval/reference changed or missing')
    return p.read_text()

def verify_risk_scope():
    decision=json.loads(verified_text('approval'))
    if decision['id']!=RISK_ID or decision['kind']!='限定研究工程风险接受':
        raise V2Error('RISK_APPROVAL_MISMATCH','Wrong risk decision')
    return decision

def reference(kind):
    if kind not in ('hemothorax','carbon_monoxide_exposure'):raise V2Error('RISK_SCOPE_NOT_AUTHORIZED','This event exception belongs only to the two fixed profiles')
    verify_risk_scope()
    if kind=='hemothorax':
        rows=list(csv.DictReader(verified_text('hemo').splitlines()))
        return {round(float(x['time_s'])):{**{k:float(x[k]) for k in PUBLIC_FIELDS},'Na':float(x['diagnostic.Sodium'])} for x in rows}
    rows=[json.loads(line) for key in ('co_pre','co_post') for line in verified_text(key).splitlines()]
    result={}
    for x in rows:
        p=x['patient_observation'];t=p['simulation_time_s']
        if abs(t-round(t))>1e-6:continue
        result[round(t)]={**{k:p[k.split('.')[0]][k.split('.')[1]]['value'] for k in PUBLIC_FIELDS},'Na':x['exposure_observation']['aorta_sodium_mEq_L']['value']}
    return result

def conformance(kind,history,pre_samples=()):
    expected=reference(kind);samples=[]
    for x in history:
        p=x.patient_observation.model_dump();t=p['simulation_time_s']
        if abs(t-round(t))>1e-6:continue
        samples.append((round(t),{**{k:(p.get(k.split('.')[0]) or {}).get(k.split('.')[1],{}).get('value') for k in PUBLIC_FIELDS},'Na':x.aorta_sodium_mEq_L.value}))
    for x in pre_samples:
        t=x['time_s']
        if abs(t-round(t))<1e-6:samples.append((round(t),x['values']))
    seen=set();failures=[];maximum=0.
    for t,values in samples:
        seen.add(t)
        for k,v in values.items():
            ref=expected.get(t,{}).get(k)
            if v is None or ref is None or not math.isfinite(v):failures.append({'time_s':t,'field':k,'reason':'missing'});continue
            delta=abs(v-ref);maximum=max(maximum,delta)
            if delta>PRECISION:failures.append({'time_s':t,'field':k,'reason':'outside_verified_trajectory','actual':v,'reference':ref})
    missing=sorted(set(expected)-seen)
    return {'passed':not failures and not missing,'risk_acceptance_id':RISK_ID,'precision':PRECISION,
        'meaning':'deterministic evidence conformance, not clinical threshold','max_absolute_difference':maximum,
        'missing_seconds':missing,'failures':failures,'samples':len(seen),'accepted_event':'Hypernatremia',
        'clinical_safety_certification':False}
