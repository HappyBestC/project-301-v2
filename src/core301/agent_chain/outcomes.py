"""Window integrals and explicit missingness; no locked fourteen-rule evaluator."""
from collections import Counter
import math


def trapezoid(samples: list, start_min: float, end_min: float) -> float | None:
    points = [(s['time_min'], s['CardiacOutput_L_min']) for s in samples
              if s.get('CardiacOutput_L_min') is not None
              and math.isfinite(s['CardiacOutput_L_min'])]
    if not points:
        return None
    total = 0.0
    for (t0, co0), (t1, co1) in zip(points, points[1:]):
        if t1 < t0:
            raise ValueError('Samples must be chronological')
        left, right = max(t0, start_min), min(t1, end_min)
        if right <= left:
            continue
        # Clip a trapezoid at an event inside a sampling interval. Never extrapolate.
        a = co0 + (co1 - co0) * (left - t0) / (t1 - t0)
        b = co0 + (co1 - co0) * (right - t0) / (t1 - t0)
        total += (a + b) * 0.5 * (right - left)
    return total


def patient_outcome(record: dict, horizon_min: float = 120.0) -> dict:
    terminal = record.get('terminal_event')
    injury_unsupported = bool(record.get('injury_unsupported'))
    # Terminal physiology takes precedence over the same advance call failing.
    engine_failure = bool(record.get('engine_failure')) and terminal is None
    if injury_unsupported:
        window = 'not_simulated'
    elif terminal:
        window = 'complete_terminal'
    elif engine_failure or not record.get('reached_horizon'):
        window = 'incomplete_engine_failure'
        engine_failure = True
    else:
        window = 'complete'
    end = min(horizon_min, terminal['time_min']) if terminal else horizon_min
    observed = None if injury_unsupported else trapezoid(record['samples'], record['arrival_time_min'], horizon_min)
    complete = window in ('complete', 'complete_terminal')
    integral = (trapezoid(record['samples'], record['arrival_time_min'], end)
                if terminal else observed) if complete else None
    last = record['samples'][-1] if window == 'complete' and record['samples'] else {}
    shock = [e['time_min'] for e in record['events'] if e['event'] == 'HypovolemicShock' and e['active']]
    return {
        'patient_id': record['patient_id'], 'arrival_time_min': record['arrival_time_min'],
        'window_status': window, 'observed_integral_CO_L': observed,
        'integral_CO_L': integral,
        'terminal_event': terminal, 'first_hypovolemic_shock_min': min(shock) if shock else None,
        'final_MAP_mmHg': last.get('MAP_mmHg'), 'final_BloodVolume_mL': last.get('BloodVolume_mL'),
        'injected_actions': sum(a.get('injected', False) for a in record['actions']),
        'accepted_actions': sum(a.get('accepted') is True for a in record['actions']),
        'unsupported_actions': sum(a.get('status') == 'ACTION_UNSUPPORTED' for a in record['actions']),
        'engine_failure': engine_failure, 'injury_unsupported': injury_unsupported,
        'treatment_incomplete': bool(record.get('treatment_incomplete')),
        'exploratory': bool(record.get('exploratory')),
        'injury_unsupported_reason': record.get('injury_unsupported'),
        'engine_failure_reason': record.get('engine_failure') if engine_failure else None,
        'unsupported_action_reasons': [{'action_id': a['action_id'], 'reason': a['reason']}
                                       for a in record['actions'] if a.get('status') == 'ACTION_UNSUPPORTED'],
    }


def _aggregate(patients: dict, *, clean: bool) -> dict:
    values, excluded = [], []
    for pid, patient in patients.items():
        reasons = []
        if patient['integral_CO_L'] is None:
            reasons.append(patient['window_status'])
        if clean:
            if patient['treatment_incomplete']:
                reasons.append('treatment_incomplete')
            if patient['exploratory']:
                reasons.append('exploratory')
        if reasons:
            excluded.append({'patient_id': pid, 'reasons': reasons})
        else:
            values.append(patient['integral_CO_L'])
    return {'total_CO_L': sum(values), 'mean_CO_L': sum(values) / len(values) if values else None,
            'denominator': len(values), 'excluded_patients': excluded}


def evaluate(execution: dict, horizon_min: float = 120.0) -> dict:
    patients = {pid: patient_outcome(record, horizon_min) for pid, record in execution.items()}
    counts = Counter(p['window_status'] for p in patients.values())
    return {'patients': patients, 'summary': {
        'patients': len(patients),
        'window_status_counts': {s: counts[s] for s in ('complete', 'complete_terminal',
                                                      'incomplete_engine_failure', 'not_simulated')},
        'deaths': sum(p['terminal_event'] is not None for p in patients.values()),
        'engine_failures': sum(p['engine_failure'] for p in patients.values()),
        'injury_unsupported': sum(p['injury_unsupported'] for p in patients.values()),
        'treatment_incomplete': sum(p['treatment_incomplete'] for p in patients.values()),
        'exploratory': sum(p['exploratory'] for p in patients.values()),
        'all_available': _aggregate(patients, clean=False),
        'clean': _aggregate(patients, clean=True),
    }}
