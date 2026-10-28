"""Scheduler minutes are global; native time has a 60-second healthy prelude."""
import copy

STABILIZATION_S = 60.0


def injury_time_s(global_min: float, arrival_min: float) -> float:
    return (global_min - arrival_min) * 60.0


def native_time_s(global_min: float, arrival_min: float) -> float:
    return STABILIZATION_S + injury_time_s(global_min, arrival_min)


def global_time_min(pulse_s: float, arrival_min: float) -> float:
    return arrival_min + (pulse_s - STABILIZATION_S) / 60.0


def build_timeline(cases: list, dispatch_input: dict, schedule: dict) -> list:
    events = [{'event': 'injury_onset', 'patient_id': p['patient_id'],
               'time_min': p['arrival_time_min'], 'location': p['location']}
              for p in cases]
    actions = {a['action_id']: a for p in dispatch_input['patients']
               for plan in p['candidate_plans'] for a in plan['actions']}
    for operation in schedule['operations']:
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
            events.append({'event': 'transport' if category == 'transports' else 'care',
                           'time_min': task['start_min'], 'patient_id': task['patient_id'],
                           'record_only': True, 'task': copy.deepcopy(task)})
    # Stable sorting preserves schedule order at equal times and injury comes first.
    return sorted(events, key=lambda e: (e['time_min'], e['event'] != 'injury_onset', e['patient_id']))
