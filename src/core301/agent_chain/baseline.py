"""Experiment-only model information and resource-ID feedback, without allocation."""
import copy
from pathlib import Path

from core301.dispatch.minimal import api
from core301.paths import PROJECT_ROOT
from core301.standard_answer.scenario import load_scenario
from core301.standard_answer.tables import TableStore, prepare_costs
from .audit import sha256

DELAYS = (0, 10, 20, 30, 45, 60, 90, 120)
HINT_CODES = frozenset(('UNKNOWN_RESOURCE', 'NOT_PERSONNEL', 'RESOURCE_LOCATION',
    'EQUIPMENT_REQUIREMENT', 'SPACE_REQUIREMENT', 'STAFF_CAPABILITY_OR_COUNT'))


def prompt_path(variant):
    names = {'L0': 'resource_schedule.md', 'L1': 'resource_schedule_objective.md',
             'L2': 'resource_schedule_triage.md'}
    if variant not in names:
        raise ValueError('Expected L0, L1 or L2')
    name = names[variant]
    return PROJECT_ROOT / 'src/core301/dispatch/prompts' / name


def baseline_config(variant, tables):
    prompt = prompt_path(variant)
    if variant == 'L1' and tables is None:
        raise ValueError('--tables is required for L1')
    config = dict(schedule_variant=variant, prompt_sha256=sha256(prompt.read_bytes()),
                  tables_sha256={}, tables=str(Path(tables).resolve()) if tables else None)
    if tables is not None:
        store = TableStore(tables)
        config['tables_sha256'] = store.hashes
        if variant == 'L1':
            context, _, specs, _ = load_scenario()
            prepare_costs(context, specs, store)  # Fail before creating a run or requesting a model.
    return config


def with_urgency(context, tables):
    result = copy.deepcopy(context)
    _, _, specs, _ = load_scenario()  # typical severity, exactly as the standard solver
    store = TableStore(tables)
    _, untreated, _ = prepare_costs(context, specs, store)
    for patient in result['patients']:
        pid = patient['patient_id']
        window = 120 - int(patient['arrival_time_min'])
        cost = untreated[pid]
        urgency = {'source': 'Pulse reaction tables, typical severity of this injury type',
            'untreated': {'terminal_event_after_injury_min': (
                round(cost.terminal_min, 1) if cost.terminal_min is not None else None),
                'co_deficit_L': round(cost.deficit_L, 1)}, 'plans': {}}
        for plan in patient['candidate_plans']:
            table = store.table(specs[pid], plan)
            points = {}
            for delay in DELAYS:
                if delay <= window:
                    value = table.cost(delay, window)
                    points[str(delay)] = {'death': bool(value.death), 'co_deficit_L': round(value.deficit_L, 1)}
            urgency['plans'][plan['plan_id']] = {'effective_after_injury_min': points}
        patient['urgency'] = urgency
    return result


def resource_hints(context, candidate, feedback):
    result = copy.deepcopy(feedback)
    if not any(c['code'] in HINT_CODES for c in result['conflicts']):
        return result
    candidate = candidate if isinstance(candidate, dict) else {}
    operations = {t['task_id']: t for t in candidate.get('operations', []) if isinstance(t, dict) and 'task_id' in t}
    care = {t['task_id']: t for t in candidate.get('care', []) if isinstance(t, dict) and 'task_id' in t}
    actions = {a['action_id']: a for p in context['patients'] for plan in p['candidate_plans'] for a in plan['actions']}
    resources = context['resources']
    nodes = resources['nodes']
    for conflict in result['conflicts']:
        if conflict['code'] not in HINT_CODES:
            continue
        task = operations.get(conflict.get('task_id')) or care.get(conflict.get('task_id'))
        hints = {'personnel': [], 'equipment': [], 'spaces': []}
        conflict['valid_resource_hints'] = hints
        if task is None:
            continue
        operation = operations.get(task.get('operation_id')) if 'operation_id' in task else task
        if not operation or operation.get('action_id') not in actions:
            continue
        rule = api.requirement(context['action_mapping'], actions[operation['action_id']],
            access_mode=operation.get('access_mode', 'new'), mode=operation.get('mode', 'start'))
        location = task.get('location')
        roles = set(rule['staff_roles'])
        if 'operation_id' in task:
            roles = {rule['care']['role']}
        elif rule['access_phase_min']:
            roles.add(rule['access']['role'])
        hints['personnel'] = sorted(p['id'] for p in resources['personnel']
            if p['location'] == location and roles.intersection(p['capabilities']))
        if 'operation_id' not in task:
            hints['equipment'] = sorted(e['id'] for e in resources['equipment']
                if e['location'] == location and e['type'] in rule['equipment'])
            kind = nodes.get(location, {}).get('type', 'vehicle')
            types = rule['space_types'].get(kind, [])
            hints['spaces'] = sorted(s['id'] for s in resources['spaces']
                if s['location'] == location and s['type'] in types)
    return result
