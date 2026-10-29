"""Render decisions without repairing or changing the optimized schedule."""
from dataclasses import asdict

from core301.dispatch.minimal.models import Schedule


def _chosen(choices, solver):
    return [key for key, variable in choices.items() if solver.Value(variable)]


def export_schedule(model, solver, diagnoses=None):
    diagnoses = diagnoses or {}
    schedule = dict(version='301.resource_schedule.v1', demonstration_only=True,
                    patient_results=[], selections={}, operations=[], transports=[], care=[])
    for pid, patient in model.patients.items():
        plan_ids = _chosen(model.plans[pid], solver)
        if not plan_ids:
            diagnosis = diagnoses.get(pid)
            if diagnosis is None:
                raise ValueError(f'{pid}: unscheduled patient requires a completed insertion diagnosis')
            schedule['patient_results'].append(dict(patient_id=pid, status='unscheduled',
                reason_code=diagnosis['reason_code'], blocking_resources=diagnosis['blocking_resources'],
                reason=('在最优排程中资源分配给了其他伤员；固定其他决策后资源不足。'
                        if diagnosis['reason_code'] == 'resource_shortage' else
                        '即使为该伤员放宽全部资源，也来不及在规划期内完成转运和整个方案。'),
                considered_alternatives=[p['plan_id'] for p in patient['candidate_plans']]))
            continue
        schedule['selections'][pid] = plan_ids[0]
        schedule['patient_results'].append(dict(patient_id=pid, status='scheduled'))
        trip = model.trips[pid]
        vehicle, destination = _chosen(trip['options'], solver)[0]
        schedule['transports'].append(dict(task_id=f'{pid}-transport', patient_id=pid, vehicle_id=vehicle,
            departure_location=list(model.r['nodes'])[solver.Value(trip['origin'])], pickup=patient['location'],
            destination=destination, **{key + '_min': float(solver.Value(trip[value])) for key, value in
                [('start', 'start'), ('load_start', 'load'), ('depart', 'depart'), ('arrive', 'arrive'),
                 ('handoff_end', 'handoff'), ('end', 'end')]}))
    for aid, op in model.operations.items():
        if not solver.Value(op.present):
            continue
        optional = lambda choices: next(iter(_chosen(choices, solver)), None)
        schedule['operations'].append(dict(task_id=aid, action_id=aid, patient_id=op.patient, plan_id=op.plan,
            location=optional(op.locations), start_min=float(solver.Value(op.start)), end_min=float(solver.Value(op.end)),
            staff_ids=[optional(slot) for slot in op.staff], equipment_ids=[optional(slot) for slot in op.equipment],
            space_id=optional(op.spaces), support_space_id=optional(op.support_spaces),
            access_mode='new', access_staff_id=optional(op.access_staff), mode='start',
            consumables=op.rule['consumables']))
        for care in op.care:
            if solver.Value(care['present']):
                schedule['care'].append(dict(task_id=care['task_id'], operation_id=aid, patient_id=op.patient,
                    location=optional(care['locations']), start_min=float(solver.Value(care['start'])),
                    end_min=float(solver.Value(care['end'])), staff_id=optional(care['staff'])))
    for key in ('operations', 'transports', 'care'):
        schedule[key].sort(key=lambda t: (t['start_min'], t['task_id']))
    return Schedule.model_validate(schedule).model_dump()


def predict(context, specs, schedule, store):
    patients = []
    operations = {op['action_id']: op for op in schedule['operations']}
    for patient in context['patients']:
        pid, arrival = patient['patient_id'], int(patient['arrival_time_min'])
        selected = schedule['selections'].get(pid)
        plan = next((p for p in patient['candidate_plans'] if p['plan_id'] == selected), patient['candidate_plans'][0])
        delay = int(operations[plan['actions'][0]['action_id']]['end_min']) - arrival if selected else 'untreated'
        table = store.table(specs[pid], plan)
        value = table.cost(delay, 120 - arrival)
        patients.append(dict(patient_id=pid, table=table.name, plan_id=selected, delay_min=delay,
            observation_window_min=120-arrival, **asdict(value), deficit10=value.deficit10,
            terminal_global_min=value.terminal_min + arrival if value.terminal_min is not None else None))
    return dict(evaluation_severity='true', patients=patients, deaths=sum(p['death'] for p in patients),
                deficit_L=sum(p['deficit_L'] for p in patients), deficit10=sum(p['deficit10'] for p in patients))
