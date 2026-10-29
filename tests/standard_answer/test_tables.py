import copy
import json

import pytest

from core301.standard_answer.tables import ReactionTable, TableStore, TableUnavailable, group_id, prepare_costs
from core301.standard_answer.scenario import load_scenario
from tests.standard_answer.helpers import table_text, write_fake_tables


def test_window_then_interpolation_conservative_death_and_terminal():
    table = ReactionTable('manual', *table_text([
        ('untreated', 73, 4, 'run', 'complete_terminal'),
        (0, None, 1, 'run', 'complete'), (5, 105, 2, 'run', 'complete_terminal'),
        (10, 90, 3, 'run', 'complete_terminal')]))
    value = table.cost(2, 100)
    assert (value.death, value.deficit_L, value.terminal_min, value.interpolated) == (0, 140, None, True)
    value = table.cost(7, 100)
    assert (value.death, value.deficit_L, value.terminal_min, value.deficit10) == (1, 240, 90, 2400)
    assert value.measured_delays == (5, 10)
    assert table.cost('untreated', 60).death == 0
    assert table.cost('untreated', 100).deficit_L == 400
    assert not table.cost(5, 120).interpolated


def test_missing_rows_are_not_used_or_extrapolated():
    table = ReactionTable('manual', *table_text([
        (0, None, 0, 'run', 'complete'), (2, 0, 50, 'error', 'complete_terminal'),
        (3, 0, 50, 'run', 'incomplete'), (5, None, 5, 'run', 'complete')]))
    assert table.cost(2, 10).deficit_L == 20
    assert table.cost(3, 10).deficit_L == 30
    with pytest.raises(TableUnavailable, match='no measured bracket'):
        table.cost(6, 10)
    with pytest.raises(TableUnavailable, match='untreated'):
        table.cost('untreated', 10)
    empty = ReactionTable('empty', *table_text([(0, None, 1, 'run', 'complete')], window_bad=100))
    with pytest.raises(TableUnavailable):
        empty.cost(0, 100)


def test_death_recovery_is_reported_without_smoothing():
    table = ReactionTable('manual', *table_text([(0, 20, 1, 'run', 'complete_terminal'), (5, None, 0, 'run', 'complete')]))
    assert table.non_monotonic(120) == [dict(table='manual', window_min=120, from_d=0, to_d=5, kind='death_to_survival')]
    assert table.cost(2, 120).death == 0
    assert table.cost(0, 120).death == 1


def test_mapping_all_ten_groups_and_plan_keys(tmp_path):
    context, specs, *_ = load_scenario()
    assert len({group_id(spec) for spec in specs.values()}) == 10
    assert group_id(specs['P01']) == 'external_hemorrhage_RightLeg__s0.4'
    assert group_id(specs['P07']) == 'hemothorax_Left__s0.8'
    assert group_id(specs['P04']) == 'carbon_monoxide_exposure__co0.005'
    assert group_id(specs['P14']) == 'environmental_hypoxia__o20.12'
    store = TableStore(write_fake_tables(tmp_path / 'tables', context, specs))
    costs, untreated, warnings = prepare_costs(context, specs, store)
    assert len(costs['P09', 'P09-plan-1'][0]) == 111
    assert untreated['P09'].deficit_L == 110
    assert not warnings
    modified = copy.deepcopy(specs['P01'])
    modified['injury']['severity'] = 0.45
    with pytest.raises(TableUnavailable, match='没有对应反应表'):
        store.table(modified, context['patients'][0]['candidate_plans'][0])
    store.save_snapshot(tmp_path / 'snapshot')
    assert TableStore(tmp_path / 'snapshot').hashes == store.hashes


def test_variants_preserve_dataset_and_typical_severity():
    context, specs, typical, _ = load_scenario({'base': 'run_002', 'overrides': {
        'P01': {'severity': .8}, 'P04': {'environment_gases': {'CarbonMonoxide': .0075}},
        'P14': {'environment_gases': {'Oxygen': .1}}}})
    assert specs['P01']['injury']['severity'] == .8
    assert typical['P01']['injury']['severity'] == .4
    assert specs['P04']['injury']['environment_gases']['Nitrogen'] == 1 - .21 - .0004 - .0075
    assert specs['P14']['injury']['environment_gases']['CarbonMonoxide'] == 0
    assert load_scenario()[1]['P01']['injury']['severity'] == .4


@pytest.mark.parametrize('pid,patch', [
    ('P01', {'location_id': 'A'}), ('P01', {'environment_gases': {'Oxygen': .1}}),
    ('P04', {'severity': .8}), ('P04', {'environment_gases': {'Oxygen': .1}}),
    ('P04', {'environment_gases': {'CarbonMonoxide': .003}}),
    ('P14', {'environment_gases': {'CarbonMonoxide': .001}}),
    ('P14', {'environment_gases': {'Oxygen': .11}}), ('P01', {'severity': float('nan')}),
    ('P17', {'severity': .8}), ('P01', {'severity': True}),
])
def test_invalid_variants_fail(pid, patch):
    with pytest.raises(ValueError):
        load_scenario({'base': 'run_002', 'overrides': {pid: patch}})
