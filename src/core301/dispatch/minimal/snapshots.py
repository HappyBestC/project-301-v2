"""Host-derived point-in-time projections of one validated candidate; no execution."""
from collections import defaultdict


def snapshot(context, schedule, holds, changes, time_min):
    horizon = context['horizon_min']
    actions = {a['action_id']: a for p in context['patients'] for pl in p['candidate_plans'] for a in pl['actions']}
    continuous = {t.task_id for t in schedule.operations
                  if context['action_mapping']['actions'][actions[t.action_id]['action_type']]['continuous']}
    patients = []
    for patient in context['patients']:
        pid = patient['patient_id']
        ops = [t for t in schedule.operations if t.patient_id == pid]
        trips = sorted([t for t in schedule.transports if t.patient_id == pid], key=lambda t: t.load_start_min)
        tasks = ops + [t for t in schedule.care if t.patient_id == pid] + trips
        location = patient['location']
        transit = False
        for t in trips:
            if t.load_start_min <= time_min < t.handoff_end_min:
                location, transit = t.vehicle_id, True
            elif t.handoff_end_min <= time_min:
                location, transit = t.destination, False
        completed = [t.action_id for t in ops if t.mode == 'start' and t.end_min <= time_min]
        support = [t.task_id for t in ops if t.task_id in continuous and t.end_min <= time_min]
        active = [t.task_id for t in tasks if t.start_min <= time_min < t.end_min]
        future = [{'task_id': t.task_id, 'start_min': t.start_min, 'end_min': t.end_min}
                  for t in sorted(tasks, key=lambda t: (t.start_min, t.task_id)) if t.start_min > time_min]
        if pid not in schedule.selections:
            progress = 'unscheduled'
        elif time_min < patient['arrival_time_min']:
            progress = 'not_arrived'
        elif transit:
            progress = 'in_transport_or_handoff'
        elif support:
            progress = 'ongoing_support_stop_unknown'
        elif active:
            progress = 'task_in_progress'
        elif completed and len(completed) == sum(t.mode == 'start' for t in ops):
            progress = 'required_operations_completed_not_treatment_end'
        elif completed:
            progress = 'some_operations_completed'
        else:
            progress = 'not_started_waiting'
        patients.append({'patient_id': pid, 'plan_status': 'scheduled' if pid in schedule.selections else 'unscheduled',
                         'progress': progress, 'location': location, 'completed_action_ids': completed,
                         'active_task_ids': active, 'ongoing_support_operation_ids': support,
                         'future_tasks': future, 'required_operations_completed': bool(ops) and
                         all(t.end_min <= time_min for t in ops if t.mode == 'start'),
                         'treatment_end_confirmed': False})
    vehicles = {}
    for vid, vehicle in context['resources']['vehicles'].items():
        state = {'location': vehicle['location'], 'phase': 'idle', 'task_id': None}
        for t in sorted([t for t in schedule.transports if t.vehicle_id == vid], key=lambda t: t.start_min):
            if time_min < t.start_min:
                break
            if time_min >= t.end_min:
                state = {'location': t.destination, 'phase': 'idle', 'task_id': None}
                continue
            state = {'task_id': t.task_id, 'available_from_min': t.end_min}
            if time_min < t.load_start_min:
                state.update(phase='empty_travel', location=None, origin=t.departure_location, destination=t.pickup)
            elif time_min < t.depart_min:
                state.update(phase='loading', location=t.pickup)
            elif time_min < t.arrive_min:
                state.update(phase='loaded_travel', location=None, origin=t.pickup, destination=t.destination)
            elif time_min < t.handoff_end_min:
                state.update(phase='handoff', location=t.destination)
            else:
                state.update(phase='turnaround', location=t.destination)
            break
        vehicles[vid] = state
    groups = defaultdict(list)
    for use in changes:
        groups[(use['location'], use['item'])].append(use)
    inventory = {}
    for location, stock in context['resources']['inventory'].items():
        inventory[location] = {}
        for item, entry in stock.items():
            uses = groups[(location, item)]
            consumed = committed = bound = future_commitment = 0
            unknown = False
            for use in uses:
                qty = use['quantity']
                promise = use.get('committed_quantity')
                promise = qty if promise is None else promise
                if qty is None or promise is None:
                    unknown = True
                    continue
                committed += promise
                if use['kind'] == 'kit':
                    delivered = qty if time_min >= use['at_min'] else 0
                    reservation_time = use['at_min']
                else:
                    elapsed = max(0, min(time_min, use['through_min']) - use['at_min'])
                    duration = use['through_min'] - use['at_min']
                    delivered = qty * elapsed / duration if duration > 0 else 0
                    reservation_time = use.get('reservation_at_min')
                    if reservation_time is None:
                        reservation_time = use['at_min']
                    if use.get('committed_quantity') is not None and time_min >= use['at_min']:
                        bound += promise - delivered
                consumed += delivered
                if time_min < reservation_time:
                    future_commitment += promise
            initial = entry['quantity']
            initial_reserved = entry.get('reserved', 0)
            inventory[location][item] = {
                'unit': entry['unit'], 'initial_quantity': initial, 'initial_reserved': initial_reserved,
                'predicted_consumed': None if unknown else consumed,
                'candidate_total_commitment': None if unknown else committed,
                'unconsumed_commitment': None if unknown else committed - consumed,
                'future_not_started_commitment': None if unknown else future_commitment,
                'patient_bound_remaining': None if unknown else bound,
                'physical_remaining': None if initial is None or unknown else initial - consumed,
                'available_after_all_candidate_commitments': None if initial is None or unknown else initial - initial_reserved - committed}
    occupied = [dict(x) for x in holds if x['start_min'] <= time_min and
                (time_min < x['end_min'] or x.get('release_status') == 'unknown')]
    return {'time_min': time_min, 'horizon_min': horizon, 'prediction_only': True,
            'treatment_executed': False, 'resources_committed': False,
            'accounting': 'Two views of the same candidate, never additive. Future candidate commitments remain unavailable.',
            'patients': patients, 'vehicles': vehicles, 'resource_occupancy': occupied, 'inventory': inventory,
            'completed_required_operations_patients': sum(p['required_operations_completed'] for p in patients),
            'support_after_planning_horizon': 'unknown_stop_not_released; future care and supply not verified'}
