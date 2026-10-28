"""Bounded feedback bookkeeping; never changes a candidate or chooses resources."""
import copy
import json


def conflict_key(error):
    return json.dumps({k:error.get(k) for k in ('code','patient_id','task_id','resource_id','interval_min',
                                               'blocking_task_id','blocking_patient_id')},sort_keys=True)


def build_feedback(context, candidate, validation, round_number, history, previous_selected):
    selected = set(candidate.get('selections', {}))
    interpretable = isinstance(candidate.get('selections'), dict) and not any(
        e['code'] in ('SCHEMA_INVALID','MODEL_JSON_INVALID') for e in validation['conflicts'])
    latest = validation['conflicts']
    latest_keys = {conflict_key(error): i for i,error in enumerate(latest)}
    for error in latest:
        key = conflict_key(error)
        row = history.setdefault(key, {'conflict':copy.deepcopy(error),'source_rounds':[],
                                      'selected_participants':[]})
        if round_number not in row['source_rounds']: row['source_rounds'].append(round_number)
        involved = {error.get('patient_id'),error.get('blocking_patient_id')} & selected
        row['selected_participants'] = sorted(set(row['selected_participants']) | involved)
    historical = []
    for key,row in history.items():
        if row['source_rounds'][0] == round_number:
            continue  # latest issues already have their complete location in conflicts
        if key in latest_keys:
            historical.append({'source_rounds':row['source_rounds'], 'current_status':'still_present',
                               'latest_conflict_index':latest_keys[key]})
        else:
            status=('undetermined' if not interpretable else 'not_triggered_after_withdrawal'
                    if set(row['selected_participants'])-selected else 'resolved_in_current_candidate')
            historical.append({'source_rounds':row['source_rounds'],'current_status':status,'conflict':row['conflict']})
    withdrawn = sorted(previous_selected-selected) if interpretable else []
    # References index historical_conflicts so removal explanations do not repeat errors.
    withdrawals = [{'patient_id':pid,'prior_conflict_refs':[
        i for i,row in enumerate(historical) if pid in (row.get('conflict',{}).get('patient_id'), row.get('conflict',{}).get('blocking_patient_id')) or
        (row.get('latest_conflict_index') is not None and pid in
         (latest[row['latest_conflict_index']].get('patient_id'),latest[row['latest_conflict_index']].get('blocking_patient_id')))]}
        for pid in withdrawn]
    return {'round':round_number,'conflicts':latest,
            'required_care_tasks':validation.get('required_care_tasks',[]),
            'personnel_evidence':validation.get('personnel_evidence',{'groups':[],'calendar_complete_for_evidence':False}),
            'historical_conflicts':historical,'withdrawn_this_round':withdrawals,
            'withdrawn_or_unscheduled_patients':sorted({p['patient_id'] for p in context['patients']}-selected),
            'patient_results':candidate.get('patient_results',[]),
            'text_reference_hints':validation.get('text_reference_hints',[]),
            'instruction':'Latest conflicts are authoritative. Historical resolved issues are not new errors; disappearance after withdrawal is not scheduling repair. Preserve and repair feasible schedules. Before withdrawing a patient, check applicable real staff/time/node/transport alternatives and report specific IDs, intervals or locations and blockers in considered_alternatives; state when checks were not completed. Personnel evidence is per current candidate/interval only, not a joint assignment guarantee. Revalidate globally after changes. Coverage need not increase monotonically; never retain an infeasible task merely for coverage.'}
