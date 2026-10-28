"""Candidate fixed-evidence risk gate. No admission authority and no V2 waivers."""
import hashlib
import json
import math
import re
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.exposure_validation import HALT_EVENTS
from .registry import patterns, CONFIG_SHA256
from .acceptance import repeat_check, reference, CYCLE
MANIFEST = PROJECT_ROOT / 'research_artifacts/v2_1_battle_composite_injuries_v0.1/validation/risk_evidence_v2.json'
MANIFEST_SHA256 = 'b7dfc22e84f0062116cb94049a95c2b15b92d6561f00e14561de4cc6ce992fd9'
ALLOWED = {0: {'MinimalHemothorax', 'Hypoxia', 'Tachycardia', 'Hypernatremia'},
           1: {'Hypoxia', 'Tachycardia'}, 2: {'Tachypnea'},
           3: {'Hypernatremia'}, 4: {'Antidiuresis', 'Hypernatremia', 'Hypoxia', 'Tachycardia'}}
FINAL_ALLOWED = {0: {'Hypoxia', 'Tachycardia', 'Hypernatremia'}, 1: set(), 2: set(),
                 3: {'Hypernatremia'}, 4: {'Antidiuresis', 'Hypernatremia'}}
def pinned(path, digest):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise V2Error('RISK_EVIDENCE_INVALID', 'Fixed composite risk evidence missing or changed')
    return path.read_text()
def evidence(index, pattern):
    m = json.loads(pinned(MANIFEST, MANIFEST_SHA256))
    approval = json.loads(pinned(PROJECT_ROOT / m['approval_path'], m['approval_sha256']))
    if pattern != patterns()[index] or m['profile_config_sha256'] != CONFIG_SHA256:
        raise V2Error('RISK_SCOPE_MISMATCH', 'Only the exact fixed composite profile is accepted')
    p = m['profiles'][str(index)]
    if p['pattern_id'] != pattern['pattern_id'] or p['profile_version'] != pattern['profile_version']:
        raise V2Error('RISK_SCOPE_MISMATCH', 'Profile version mismatch')
    if index != 1 and approval['profiles'][pattern['pattern_id']]['profile'] != pattern['profile_version']:
        raise V2Error('RISK_SCOPE_MISMATCH', 'User decision does not cover profile')
    rows = [json.loads(s) for s in pinned(PROJECT_ROOT / p['events_path'], p['events_sha256']).splitlines()]
    return approval, rows

def event_match(actual, expected):
    """Compare every recorded native transition, including subsecond durations."""
    if len(actual) != len(expected): return False
    for a, b in zip(actual, expected):
        if set(a) != set(b) or set(a['events']) != set(b['events']): return False
        values = [(a['time_s'], b['time_s'])] + [(a['events'][k], b['events'][k]) for k in a['events']]
        if any(not isinstance(x, (int,float)) or not isinstance(y, (int,float)) or
               not math.isfinite(x) or not math.isfinite(y) or abs(x-y)>1e-7 for x,y in values): return False
    return True

def assess(index, pattern, rows, native_events, pulse_log, endpoint_state):
    approval, expected_events = evidence(index, pattern)
    end = pattern['simulation_timeline']['end_s']
    repeat = repeat_check(rows, reference(index, 'treated'), end)
    all_events = set().union(*(set(r['events']) for r in native_events), *(set(r['events']) for r in rows)) - CYCLE
    final = set(rows[-1]['events']) - CYCLE
    critical = bool(all_events & (set(HALT_EVENTS) | {'BrainOxygenDeficit'}))
    exact_events = event_match(native_events, expected_events)
    unexpected = all_events - ALLOWED[index]
    numeric = {'applicable': index == 0, 'passed': True}
    if index == 0:
        # Independent composite interpretation: fixed 30 mL/min, 0.02 s native step.
        negative = [r for r in rows if r['diagnostics'].get('residual_blood_volume_mL') is not None and r['diagnostics']['residual_blood_volume_mL'] < 0]
        active = endpoint_state.get('ActiveActions', {}).get('AnyAction', [])
        names = {k for a in active for k in a.get('PatientAction', {})}
        auto = re.findall(r'\[([0-9.]+)\(s\)\] Left Tube Thoracostomy has removed all blood. Setting flow rate to 0\.', pulse_log)
        raw = [r['diagnostics']['residual_blood_volume_mL'] for r in negative]
        ok = bool(raw) and len(auto)==1 and abs(float(auto[0])-715.58)<=1e-7 and min(raw)>=-.01 and max(raw)-min(raw)<=1e-7
        ok = ok and not names & {'Hemothorax', 'TubeThoracostomy'} and all(r['diagnostics']['tube_flow_mL_min'] is None and r['diagnostics']['source_flow_mL_s'] is None for r in negative)
        numeric = {'applicable':True, 'passed':bool(ok), 'version':'301.v2_1.thoracic.numeric.2', 'raw_min_mL': min(raw) if raw else None, 'normalized_value':None, 'inherited_v2_approval':False}
    passed = repeat['passed'] and exact_events and not critical and not unexpected and final <= FINAL_ALLOWED[index] and numeric['passed']
    return {'passed':bool(passed), 'version':'301.v2_1.risk_gate.2', 'risk_acceptance_id':approval['risk_acceptance_id'] if index != 1 else None,
            'accepted_risk_exemptions':sorted(ALLOWED[index] - ({'MinimalHemothorax'} if index==0 else {'Hypoxia','Tachycardia'})),
            'unreviewed_events':sorted(unexpected), 'final_events':sorted(final), 'critical_veto':critical,
            'full_transition_match':exact_events, 'approved_trajectory_match':repeat, 'numeric_review':numeric,
            'clinical_safety':'NOT_CERTIFIED', 'production_enabled':False, 'automatic_admission':False}
