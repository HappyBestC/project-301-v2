"""V1.1 data invariants and field/vehicle rules in the unchanged validator."""
import copy
import itertools

import pytest

from core301.dispatch.minimal import api
from core301.dispatch.minimal.validation import validate_schedule
from core301.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/medical_resources_v1_1'
DATASET = PROJECT_ROOT / 'dataset_v1/run_002'
FIELD_ROUTES = {
    'F1': {'A': 8, 'B': 18, 'H1': 18, 'H2': 28, 'F1': 0, 'F2': 20},
    'F2': {'A': 16, 'B': 8, 'H1': 26, 'H2': 16, 'F1': 20, 'F2': 0},
}


def test_v1_1_actions_are_byte_identical():
    assert (CONFIG / 'actions.json').read_bytes() == (api.CONFIG / 'actions.json').read_bytes()


def test_resources_change_only_the_four_specified_fields():
    old = api.read(api.CONFIG / 'resources.json')
    new = api.read(CONFIG / 'resources.json')
    expected = copy.deepcopy(old)
    expected['version'] = '301.medical_resources.v1.1'
    expected['nodes'].update({'F1': {'type': 'field'}, 'F2': {'type': 'field'}})
    expected['travel_min'].update(copy.deepcopy(FIELD_ROUTES))
    for node in old['nodes']:
        for field in FIELD_ROUTES:
            expected['travel_min'][node][field] = FIELD_ROUTES[field][node]
    expected['notes'].append('Field nodes F1/F2 (V1.1): casualty locations only; no personnel, '
                            'equipment, spaces or inventory; no treatment can start there.')
    assert new == expected
    assert {k for k in old if old[k] != new[k]} == {'version', 'nodes', 'travel_min', 'notes'}
    for key in ('personnel', 'equipment', 'spaces'):
        assert all(a['location'] not in FIELD_ROUTES for a in new[key])


def test_complete_symmetric_metric_preserves_old_routes():
    old = api.read(api.CONFIG / 'resources.json')['travel_min']
    travel = api.read(CONFIG / 'resources.json')['travel_min']
    nodes = {'A', 'B', 'H1', 'H2', 'F1', 'F2'}
    assert set(travel) == nodes
    assert all(set(row) == nodes for row in travel.values())
    for a, b, c in itertools.product(nodes, repeat=3):
        assert travel[a][a] == 0
        assert travel[a][b] == travel[b][a]
        assert travel[a][b] <= travel[a][c] + travel[c][b]
        if a in old and b in old:
            assert travel[a][b] == old[a][b]


def test_v1_1_source_digests_validate():
    resources, mapping = api.load_config(CONFIG)
    assert resources['version'] == '301.medical_resources.v1.1'
    assert mapping == api.load_config()[1]
    assert len(mapping['actions']) == 12
    assert all('field' not in a['allowed_start'] for a in mapping['actions'].values())


@pytest.mark.parametrize('filename', ['patient_specs.json', 'patients_initial.json'])
def test_run_002_changes_only_locations(filename):
    old = api.read(api.DATASET / filename)
    expected = copy.deepcopy(old)
    for patient in expected:
        patient['location_id'] = {'A': 'F1', 'B': 'F2'}[patient['location_id']]
    assert api.read(DATASET / filename) == expected


def test_run_002_copies_exactly_the_required_templates_and_observations():
    files = {'patient_specs.json', 'patients_initial.json', 'action_plan_templates.json', 'README.md'}
    observations = {f'patient_observations/P{i:02}.json' for i in range(1, 17)}
    assert {str(p.relative_to(DATASET)) for p in DATASET.rglob('*') if p.is_file()} == files | observations
    for name in observations | {'action_plan_templates.json'}:
        assert (DATASET / name).read_bytes() == (api.DATASET / name).read_bytes()


def test_load_cases_preserves_everything_except_location():
    expected = api.load_cases()
    for patient in expected:
        patient['location'] = {'A': 'F1', 'B': 'F2'}[patient['location']]
    actual = api.load_cases(DATASET)
    assert len(actual) == 16 and actual == expected


def field_schedule(pid='P10', *, start=10.0, pickup=None):
    resources, mapping = api.load_config(CONFIG)
    patient = next(p for p in api.load_cases(DATASET) if p['patient_id'] == pid)
    context = api.build_input(resources, mapping, [patient])
    plan = patient['candidate_plans'][0]
    assert len(plan['actions']) == 1
    action = plan['actions'][0]
    rule = mapping['actions'][action['action_type']]
    assert not rule['continuous']
    vehicle, station = ('V1', 'A') if pid == 'P10' else ('V2', 'B')
    pickup = pickup or patient['location']
    load = start + resources['travel_min'][station][pickup]
    depart = load + 3
    arrive = depart + resources['travel_min'][pickup][station]
    handoff = arrive + 5
    transport = {'task_id': 'trip', 'patient_id': pid, 'vehicle_id': vehicle,
                 'departure_location': station, 'pickup': pickup, 'destination': station,
                 'start_min': start, 'load_start_min': load, 'depart_min': depart,
                 'arrive_min': arrive, 'handoff_end_min': handoff, 'end_min': handoff + 5}
    operation = {'task_id': 'treat', 'patient_id': pid, 'plan_id': plan['plan_id'],
                 'action_id': action['action_id'], 'location': station,
                 'start_min': handoff, 'end_min': handoff + rule['duration_min'],
                 'staff_ids': [station + '-basic-1'], 'space_id': station + '-treatment-1',
                 'equipment_ids': [], 'consumables': copy.deepcopy(rule['consumables'])}
    return context, {'demonstration_only': True, 'patient_results': [{'patient_id': pid, 'status': 'scheduled'}],
                     'selections': {pid: plan['plan_id']}, 'operations': [operation],
                     'transports': [transport], 'care': []}


def in_vehicle(schedule):
    trip, operation = schedule['transports'][0], schedule['operations'][0]
    duration = operation['end_min'] - operation['start_min']
    vehicle = trip['vehicle_id']
    operation.update(location=vehicle, start_min=trip['depart_min'], end_min=trip['depart_min'] + duration,
                     staff_ids=[vehicle + '-medic-1'], space_id=vehicle + '-stretcher-1')
    assert trip['load_start_min'] <= operation['start_min'] < operation['end_min'] <= trip['handoff_end_min']


def test_p10_pickup_then_station_dressing_has_zero_conflicts():
    context, schedule = field_schedule()
    result = validate_schedule(context, schedule)
    assert result['conflicts'] == []
    assert result['scheduled_patients'] == 1


def test_p10_field_dressing_is_rejected():
    context, schedule = field_schedule()
    schedule['operations'][0].update(location='F1', start_min=10.0, end_min=12.0)
    result = validate_schedule(context, schedule)
    assert 'LOCATION_UNSUPPORTED' in {c['code'] for c in result['conflicts']}


def test_p10_dressing_in_vehicle_has_zero_conflicts():
    context, schedule = field_schedule()
    in_vehicle(schedule)
    assert validate_schedule(context, schedule)['conflicts'] == []


def test_p05_decompression_in_vehicle_is_rejected():
    context, schedule = field_schedule('P05', start=0.0)
    in_vehicle(schedule)
    result = validate_schedule(context, schedule)
    assert 'LOCATION_UNSUPPORTED' in {c['code'] for c in result['conflicts']}


def test_p10_departing_before_injury_is_rejected():
    context, schedule = field_schedule(start=9.0)
    result = validate_schedule(context, schedule)
    assert 'BEFORE_ARRIVAL' in {c['code'] for c in result['conflicts']}


def test_p10_incorrect_pickup_is_rejected():
    context, schedule = field_schedule(pickup='A')
    result = validate_schedule(context, schedule)
    assert 'PATIENT_LOCATION' in {c['code'] for c in result['conflicts']}
