import copy

import pytest

from core301.dispatch.minimal.validation import validate_schedule
from core301.standard_answer.export import export_schedule
from tests.standard_answer.helpers import context_for, make_model, scheduled, solve_model


@pytest.fixture(scope='module')
def samples():
    return {key: scheduled(*args) for key, args in {
        'simple': ('P05', 1), 'blood': ('P01', 2), 'vent': ('P03', 1), 'drain': ('P07', 1)
    }.items()} | {'oxygen': scheduled('P12', onboard=True)}


def _duplicate_operation(schedule, *, other_space=False):
    operation = copy.deepcopy(schedule['operations'][-1])
    operation['task_id'] += '-duplicate'
    if other_space:
        operation['space_id'] = next(x for x in ('H1-ventilation_bed-1', 'H1-ventilation_bed-2') if x != operation['space_id'])
    schedule['operations'].append(operation)


def _dependency(schedule):
    first, second = schedule['operations']
    length = second['end_min'] - second['start_min']
    second.update(start_min=first['end_min'] - 1, end_min=first['end_min'] - 1 + length)


@pytest.mark.parametrize('sample,code,mutate', [
    ('simple', 'VEHICLE_POSITION', lambda s: s['transports'][0].update(departure_location='B')),
    ('simple', 'TRANSPORT_TIMING', lambda s: s['transports'][0].update(arrive_min=1.0)),
    ('simple', 'OUTSIDE_HORIZON', lambda s: s['transports'][0].update(end_min=121.0)),
    ('simple', 'OUTSIDE_HORIZON', lambda s: s['operations'][0].update(end_min=121.0)),
    ('simple', 'VEHICLE_OVERLAP', lambda s: s['transports'].append({**s['transports'][0], 'task_id': 'overlapping-trip'})),
    ('oxygen', 'BEFORE_ARRIVAL', lambda s: s['transports'][0].update(start_min=0.0)),
    ('oxygen', 'BEFORE_ARRIVAL', lambda s: s['operations'][0].update(start_min=0.0, end_min=2.0)),
    ('oxygen', 'STAFF_CAPABILITY_OR_COUNT', lambda s: s['care'][0].update(staff_id='V1-driver-1')),
    ('simple', 'PATIENT_LOCATION', lambda s: s['transports'][0].update(pickup='F1')),
    ('simple', 'PATIENT_LOCATION', lambda s: s['operations'][0].update(location='A')),
    ('simple', 'LOCATION_UNSUPPORTED', lambda s: s['operations'][0].update(location='F2')),
    ('simple', 'ACTION_DURATION', lambda s: s['operations'][0].update(end_min=100.0)),
    ('simple', 'PLAN_ACTION_MISSING', lambda s: s.update(operations=[])),
    ('simple', 'DUPLICATE_ACTION', _duplicate_operation),
    ('simple', 'STAFF_CAPABILITY_OR_COUNT', lambda s: s['operations'][0].update(staff_ids=['H1-triage-1'])),
    ('simple', 'RESOURCE_LOCATION', lambda s: s['operations'][0].update(staff_ids=['A-basic-1'])),
    ('simple', 'SPACE_REQUIREMENT', lambda s: s['operations'][0].update(space_id='H1-bed-1')),
    ('simple', 'CONSUMABLE_MAPPING_MISMATCH', lambda s: s['operations'][0].update(consumables={})),
    ('simple', 'ELIGIBILITY_REQUIRED', lambda s: s.update(demonstration_only=False)),
    ('blood', 'DEPENDENCY_UNMET', _dependency),
    ('blood', 'ACCESS_STAFF_REQUIRED', lambda s: s['operations'][-1].update(access_staff_id=None)),
    ('blood', 'STAFF_CAPABILITY_OR_COUNT', lambda s: s['operations'][-1].update(staff_ids=[])),
    ('blood', 'CARE_MISSING', lambda s: s.update(care=s['care'][1:])),
    ('blood', 'CARE_TIMING', lambda s: s['care'][0].update(start_min=s['care'][0]['start_min'] + .5)),
    ('blood', 'DUPLICATE_CARE', lambda s: s['care'].append({**s['care'][0], 'task_id': 'duplicated-care'})),
    ('blood', 'PATIENT_LOCATION', lambda s: s['care'][0].update(location='A')),
    ('vent', 'EQUIPMENT_REQUIREMENT', lambda s: s['operations'][0].update(equipment_ids=[])),
    ('vent', 'DOUBLE_POSITION', lambda s: _duplicate_operation(s, other_space=True)),
    ('drain', 'SUPPORT_SPACE_REQUIRED', lambda s: s['operations'][-1].update(support_space_id=None)),
    ('drain', 'SUPPORT_SPACE_REQUIREMENT', lambda s: s['operations'][-1].update(support_space_id='H1-treatment-1')),
    ('simple', 'PATIENT_RESULT_MISSING', lambda s: s.update(patient_results=[])),
    ('simple', 'PATIENT_RESULT_DUPLICATE', lambda s: s['patient_results'].append(copy.deepcopy(s['patient_results'][0]))),
    ('simple', 'SCHEMA_INVALID', lambda s: s['operations'][0].update(staff_ids=['H1-basic-1', 'H1-basic-1'])),
])
def test_validator_rejects_each_rule_mutation(samples, sample, code, mutate):
    context, _, _, original = samples[sample]
    assert validate_schedule(context, original)['conflicts'] == []
    schedule = copy.deepcopy(original)
    mutate(schedule)
    assert code in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}


@pytest.mark.parametrize('code,change', [
    ('RESOURCE_UNAVAILABLE', lambda a: a.update(status='unavailable')),
    ('RESOURCE_UNAVAILABLE', lambda a: a.update(available_from_min=119)),
    ('RESOURCE_BOUND', lambda a: a.update(bound_patient_id='P01')),
])
def test_asset_guards_match_validator_and_model(samples, code, change):
    context, _, _, schedule = samples['simple']
    context = copy.deepcopy(context)
    rid = schedule['operations'][0]['staff_ids'][0]
    change(next(a for a in context['resources']['personnel'] if a['id'] == rid))
    assert code in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    op = model.operations['P05-plan-1-a1']
    model.cp.Add(op.staff[0][rid] == 1)
    model.cp.Add(op.start == int(schedule['operations'][0]['start_min']))
    solve_model(model, feasible=False)


@pytest.mark.parametrize('constraint', ['duration', 'before_arrival', 'outside_horizon', 'patient_location', 'missing_action',
                                        'two_plans', 'new_access', 'dependency', 'followup', 'two_destinations'])
def test_forced_invalid_decisions_are_infeasible(constraint):
    pid = 'P09'
    model = make_model(context_for(pid))
    a, b = model.operations[f'{pid}-plan-2-a1'], model.operations[f'{pid}-plan-2-a2']
    trip = model.trips[pid]
    model.cp.Add(a.present == 1)
    if constraint == 'duration': model.cp.Add(a.end - a.start == 4)
    elif constraint == 'before_arrival': model.cp.Add(trip['start'] == 0)
    elif constraint == 'outside_horizon': model.cp.Add(trip['end'] == 121)
    elif constraint == 'patient_location':
        model.cp.Add(a.locations['H1'] == 1)
        model.cp.Add(a.start < trip['handoff'])
    elif constraint == 'missing_action': model.cp.Add(b.present == 0)
    elif constraint == 'two_plans': model.cp.Add(model.plans[pid][f'{pid}-plan-1'] == 1)
    elif constraint == 'new_access': model.cp.Add(b.end - b.start == 8)
    elif constraint == 'dependency': model.cp.Add(b.start < a.end)
    elif constraint == 'followup': model.cp.Add(b.start == a.end + 1)
    elif constraint == 'two_destinations':
        model.cp.Add(trip['destinations']['H1'] == 1)
        model.cp.Add(trip['destinations']['H2'] == 1)
    solve_model(model, feasible=False)


def test_initial_reservation_and_personnel_overlap(samples):
    context, _, _, schedule = samples['simple']
    context = copy.deepcopy(context)
    op = schedule['operations'][0]
    rid = op['staff_ids'][0]
    context['resources']['initial_reservations'] = [dict(resource_id=rid, patient_id='P99', task_id='existing',
        kind='operation', start_min=0, end_min=120)]
    assert 'RESOURCE_OVERLAP' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    model.cp.Add(model.operations[op['action_id']].staff[0][rid] == 1)
    solve_model(model, feasible=False)


def test_vehicle_unavailable_and_first_position(samples):
    context, _, _, schedule = samples['simple']
    context = copy.deepcopy(context)
    context['resources']['vehicles']['V1']['status'] = 'unavailable'
    assert 'VEHICLE_UNAVAILABLE' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    model.cp.Add(model.trips['P05']['vehicles']['V1'] == 1)
    solve_model(model, feasible=False)
    model = make_model(context_for('P05'))
    model.cp.Add(model.trips['P05']['vehicles']['V1'] == 1)
    model.cp.Add(model.trips['P05']['origin'] == list(model.r['nodes']).index('B'))
    solve_model(model, feasible=False)


def test_vehicle_overlap_is_impossible():
    model = make_model(context_for('P05', 'P11'))
    for pid in ('P05', 'P11'):
        model.cp.Add(model.trips[pid]['vehicles']['V1'] == 1)
        model.cp.Add(model.trips[pid]['start'] == 10)
    solve_model(model, feasible=False)


def test_full_saline_commitment_even_at_horizon():
    context = context_for('P08')
    context['resources']['inventory']['H1']['saline']['quantity'] = 499
    model = make_model(context)
    op = model.operations['P08-plan-1-a1']
    model.cp.Add(op.locations['H1'] == 1)
    model.cp.Add(op.end == 120)
    solve_model(model, feasible=False)


def test_oxygen_debit_and_vehicle_crew_exemption(samples):
    context, _, _, schedule = samples['oxygen']
    assert schedule['operations'][0]['location'] == 'V1'
    assert {c['location'] for c in schedule['care']} == {'V1', 'H1'}
    assert validate_schedule(context, schedule)['conflicts'] == []
    context = copy.deepcopy(context)
    context['resources']['inventory']['V1']['oxygen']['quantity'] = 44
    assert 'STOCK_SHORTAGE' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    op = model.operations['P12-plan-1-a1']
    model.cp.Add(op.locations['V1'] == 1)
    model.cp.Add(op.end == 30)
    solve_model(model, feasible=False)


def test_mechanical_ventilation_oxygen_is_out_of_scope(samples):
    context, _, _, schedule = samples['vent']
    context = copy.deepcopy(context)
    context['resources']['inventory']['H1']['oxygen']['quantity'] = 0
    assert validate_schedule(context, schedule)['conflicts'] == []
    model = make_model(context)
    model.cp.Add(model.operations['P03-plan-1-a2'].locations['H1'] == 1)
    assert validate_schedule(context, export_schedule(model, solve_model(model)))['conflicts'] == []


def test_continuous_equipment_cannot_be_shared():
    model = make_model(context_for('P03', 'P13'))
    for pid in ('P03', 'P13'):
        op = model.operations[pid + '-plan-1-a2']
        model.cp.Add(op.equipment[0]['H1-ventilator-1'] == 1)
    solve_model(model, feasible=False)


def test_research_capacity_and_mandatory_support(samples):
    context, _, _, schedule = samples['drain']
    context = copy.deepcopy(context)
    context['resources']['service_capacities'] = []
    assert 'RESEARCH_CAPACITY' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    model.cp.Add(model.selected['P07'] == 1)
    solve_model(model, feasible=False)
    model = make_model(context_for('P07'))
    op = model.operations['P07-plan-1-a2']
    model.cp.Add(op.present == 1)
    model.cp.Add(sum(op.support_spaces.values()) == 0)
    solve_model(model, feasible=False)


def test_same_space_gap_is_reserved():
    model = make_model(context_for('P07', 'P05'), max_followup_gap=10)
    a = model.operations['P07-plan-1-a1']
    b = model.operations['P07-plan-1-a2']
    other = model.operations['P05-plan-1-a1']
    for op in (a, b, other):
        model.cp.Add(op.spaces['H1-treatment-1'] == 1)
    model.cp.Add(a.start == 60)
    model.cp.Add(b.start == 85)
    model.cp.Add(other.start == 78)
    solve_model(model, feasible=False)


def test_access_phase_distinct_main_staff_and_template_gap(samples):
    _, _, _, schedule = samples['blood']
    a, b = schedule['operations']
    assert b['end_min'] - b['start_min'] == 11
    assert b['start_min'] == a['end_min']
    assert len(set(b['staff_ids'])) == 2 and b['access_staff_id']
    assert b['access_mode'] == 'new' and b['mode'] == 'start'
    assert b['consumables'] == {'transfusion_set': 1, 'iv_access_kit': 1}


def test_equipment_turnaround_is_reserved(samples):
    context, _, _, schedule = samples['vent']
    context = copy.deepcopy(context)
    operation = schedule['operations'][0]
    rid, end = operation['equipment_ids'][0], operation['end_min']
    context['resources']['initial_reservations'] = [dict(resource_id=rid, patient_id='P99', task_id='turnaround-blocker',
        kind='equipment', start_min=end, end_min=end+5)]
    assert 'RESOURCE_OVERLAP' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    op = model.operations[operation['action_id']]
    model.cp.Add(op.equipment[0][rid] == 1)
    model.cp.Add(op.end == int(end))
    solve_model(model, feasible=False)


def test_blood_full_commitment_and_kit_stock(samples):
    for sample, item in [('blood', 'blood'), ('simple', 'decompression_kit')]:
        context, _, _, schedule = samples[sample]
        context = copy.deepcopy(context)
        context['resources']['inventory']['H1'][item]['quantity'] = 499 if item == 'blood' else 0
        assert 'STOCK_SHORTAGE' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
        model = make_model(context)
        op = model.operations[schedule['operations'][-1]['action_id']]
        model.cp.Add(op.locations['H1'] == 1)
        if item == 'blood':
            model.cp.Add(op.end == 120)
        solve_model(model, feasible=False)


def test_double_position_against_initial_patient_bed(samples):
    context, _, _, schedule = samples['vent']
    context = copy.deepcopy(context)
    used = schedule['operations'][-1]['space_id']
    other = next(s['id'] for s in context['resources']['spaces'] if s['location'] == 'H1' and s['type'] == 'ventilation_bed' and s['id'] != used)
    context['resources']['initial_reservations'] = [dict(resource_id=other, patient_id='P03', task_id='ongoing-bed',
        kind='space', start_min=0, end_min=120)]
    assert 'DOUBLE_POSITION' in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
    model = make_model(context)
    model.cp.Add(model.operations['P03-plan-1-a2'].spaces[used] == 1)
    solve_model(model, feasible=False)


@pytest.mark.parametrize('code,patch', [
    ('UNSCHEDULED_REASON_REQUIRED', {'reason': '资源不足'}),
    ('ALTERNATIVES_REQUIRED', {'considered_alternatives': []}),
    ('BLOCKING_RESOURCE_REQUIRED', {'blocking_resources': []}),
    ('REASON_UNKNOWN_REFERENCE', {'blocking_resources': ['V99']}),
])
def test_unscheduled_accounting_requirements(samples, code, patch):
    context, _, _, _ = samples['simple']
    result = dict(patient_id='P05', status='unscheduled', reason_code='resource_shortage',
        reason='在最优排程中资源分配给了其他伤员，车辆资源无法满足。',
        blocking_resources=['V1'], considered_alternatives=['P05-plan-1'])
    schedule = dict(demonstration_only=True, selections={}, operations=[], transports=[], care=[], patient_results=[result])
    assert not validate_schedule(context, schedule)['conflicts']
    result.update(patch)
    assert code in {c['code'] for c in validate_schedule(context, schedule)['conflicts']}
