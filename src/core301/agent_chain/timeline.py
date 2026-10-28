"""Scheduler minutes are global; native time has a 60-second healthy prelude."""
import copy

STABILIZATION_S = 60.0
TREATMENT_STATUSES = ('scheduled', 'unscheduled', 'treatment_excluded', 'no_schedule')
TREATMENT_FIELDS = ('treatment_status', 'unscheduled_reason_code', 'unscheduled_reason',
                    'treatment_exclusion_reason')


def injury_time_s(global_min: float, arrival_min: float) -> float:
    return (global_min - arrival_min) * 60.0


def native_time_s(global_min: float, arrival_min: float) -> float:
    return STABILIZATION_S + injury_time_s(global_min, arrival_min)


def global_time_min(pulse_s: float, arrival_min: float) -> float:
    return arrival_min + (pulse_s - STABILIZATION_S) / 60.0


def build_timeline(cases: list, dispatch_input: dict | None, schedule: dict | None, *,
                   excluded_patients: dict | None = None) -> list:
    excluded = excluded_patients or {}
    results = {r['patient_id']: r for r in schedule['patient_results']} if schedule is not None else {}
    events = []
    for patient in cases:
        pid = patient['patient_id']
        if pid in excluded:
            treatment = {'treatment_status': 'treatment_excluded',
                         'treatment_exclusion_reason': copy.deepcopy(excluded[pid])}
        elif schedule is None:
            treatment = {'treatment_status': 'no_schedule'}
        elif pid in schedule['selections']:
            treatment = {'treatment_status': 'scheduled'}
        else:
            treatment = {'treatment_status': 'unscheduled',
                         'unscheduled_reason_code': results[pid]['reason_code'],
                         'unscheduled_reason': results[pid]['reason']}
        events.append({'event': 'injury_onset', 'patient_id': pid, 'time_min': patient['arrival_time_min'],
                       'location': patient['location'], **treatment})
    if schedule is None:
        return sorted(events, key=lambda e: (e['time_min'], e['patient_id']))
    selected = {e['patient_id'] for e in events if e['treatment_status'] == 'scheduled'}
    actions = {a['action_id']: a for p in dispatch_input['patients']
               for plan in p['candidate_plans'] for a in plan['actions']}
    for operation in schedule['operations']:
        if operation['patient_id'] not in selected:
            continue
        action = actions[operation['action_id']]
        if operation['mode'] == 'start':
            events.append({
                'event': 'apply_action', 'patient_id': operation['patient_id'],
                'task_id': operation['task_id'], 'action_id': operation['action_id'],
                'action_type': action['action_type'], 'target': copy.deepcopy(action['target']),
                'location': operation['location'], 'time_min': operation['end_min'],
            })
        else:
            events.append({'event': 'operation_continue', 'time_min': operation['start_min'],
                           'patient_id': operation['patient_id'], 'record_only': True,
                           'operation': copy.deepcopy(operation)})
    for category in ('transports', 'care'):
        for task in schedule[category]:
            if task['patient_id'] not in selected:
                continue
            events.append({'event': 'transport' if category == 'transports' else 'care',
                           'time_min': task['start_min'], 'patient_id': task['patient_id'],
                           'record_only': True, 'task': copy.deepcopy(task)})
    # Stable sorting preserves schedule order at equal times and injury comes first.
    return sorted(events, key=lambda e: (e['time_min'], e['event'] != 'injury_onset', e['patient_id']))
