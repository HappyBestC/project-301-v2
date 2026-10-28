"""Read-only personnel evidence from the validator's own demands and reservations."""

def asset_problems(asset, patient_id, start, location):
    problems = []
    if asset['location'] != location:
        problems.append(('RESOURCE_LOCATION', 'Resource is not at task location'))
    if asset.get('status') != 'available' or asset.get('available_from_min', 0) > start:
        problems.append(('RESOURCE_UNAVAILABLE', 'Resource unavailable at requested time'))
    if asset.get('bound_patient_id') not in (None, patient_id):
        problems.append(('RESOURCE_BOUND', 'Resource bound to another patient'))
    return problems


def personnel_overlap_exempt(a, b):
    return (a['task_id'] == b['task_id'] or
            (a['patient_id'] == b['patient_id'] and 'crew' in (a['kind'], b['kind']) and a['kind'] != b['kind']))


def personnel_evidence(people, demands, holds, conflicts, eps):
    relevant = set()
    for error in conflicts:
        code = error['code']; resource = error.get('resource_id')
        if code in ('STAFF_CAPABILITY_OR_COUNT', 'NOT_PERSONNEL', 'ACCESS_STAFF_REQUIRED') or (
                code in ('RESOURCE_OVERLAP', 'RESOURCE_LOCATION', 'RESOURCE_UNAVAILABLE', 'RESOURCE_BOUND', 'UNKNOWN_RESOURCE')
                and (resource in people or any(resource in d['assigned_ids'] for d in demands))):
            relevant.update(x for x in (error.get('task_id'), error.get('blocking_task_id')) if x)
    # Invalid/unresolved tasks may have been skipped before staff reservations were
    # generated. Do not advertise free personnel from an incomplete calendar.
    incomplete = any(x['code'] in ('SCHEMA_INVALID', 'UNKNOWN_PATIENT', 'UNKNOWN_ACTION',
                     'UNKNOWN_PLAN', 'CARE_TIMING', 'CARE_MISSING', 'UNKNOWN_VEHICLE', 'UNKNOWN_NODE') for x in conflicts)
    groups = {}
    for d in demands:
        if d['task_id'] not in relevant:
            continue
        key = (d['patient_id'], d['operation_id'] or d['task_id'], d['location'], tuple(d['roles']))
        group = groups.setdefault(key, {'patient_id': d['patient_id'], 'operation_id': d['operation_id'],
                    'required_capabilities': d['roles'], 'location': d['location'], 'segments': [], 'candidates': []})
        group['segments'].append(d)
    for group in groups.values():
        for sid, person in people.items():
            matched = sorted(set(group['required_capabilities']) & set(person['capabilities']))
            if not matched:
                continue
            candidate = {'personnel_id': sid, 'location': person['location'], 'capabilities': person['capabilities'],
                         'matched_capabilities': matched, 'status': person['status'],
                         'available_from_min': person.get('available_from_min', 0), 'segments': []}
            for d in group['segments']:
                query = dict(resource_id=sid, patient_id=d['patient_id'], task_id=d['task_id'], kind='operation')
                blocked = []
                for h in holds:
                    if h['resource_id'] != sid or personnel_overlap_exempt(h, query):
                        continue
                    lo, hi = max(d['start_min'], h['start_min']), min(d['end_min'], h['end_min'])
                    if lo < hi - eps:
                        blocked.append({'task_id': h['task_id'], 'patient_id': h['patient_id'],
                                        'interval_min': [lo, hi], 'kind': h['kind']})
                reasons = [code for code, _ in asset_problems(person, d['patient_id'], d['start_min'], d['location'])]
                if blocked: reasons.append('RESOURCE_OVERLAP')
                # Distinct roles in a multi-person operation cannot be filled twice
                # by the same already-assigned person, even when self-task holds overlap.
                assigned = sid in d['assigned_ids']
                state = 'unavailable' if reasons else 'undetermined' if incomplete else 'already_assigned_this_phase' if assigned else 'free_for_this_interval'
                candidate['segments'].append({'task_id': d['task_id'], 'interval_min': [d['start_min'], d['end_min']],
                    'availability': state, 'reasons': reasons, 'conflicting_tasks': blocked})
            group['candidates'].append(candidate)
    missing = sorted(relevant - {d['task_id'] for d in demands})
    return {'scope': 'Evidence only for current candidate and each listed interval; no assignment or repair. Multiple replacements require full revalidation. Distinct staff must cover all roles.',
            'calendar_complete_for_evidence': not incomplete, 'groups': list(groups.values()),
            'undetermined_task_ids': missing}
