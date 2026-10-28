import ast
import copy
from pathlib import Path

import pytest

from core301.agent_chain import outcomes, timeline


def test_timeline_only_start_operations_inject_at_end(chain_data):
    cases, _, context, schedule = chain_data
    continuation = {**schedule['operations'][0], 'mode': 'continue', 'task_id': 'continued',
                    'start_min': 12.0, 'end_min': 15.0}
    schedule['operations'].append(continuation)
    events = timeline.build_timeline(cases, context, schedule)
    applied = {e['task_id']: e for e in events if e['event'] == 'apply_action'}
    assert len(applied) == len(schedule['operations']) - 1
    for operation in schedule['operations'][:-1]:
        assert applied[operation['task_id']]['time_min'] == operation['end_min']
        assert applied[operation['task_id']]['location'] == operation['location']
    assert 'continued' not in applied
    assert len([e for e in events if e['event'] == 'injury_onset']) == 16
    assert len([e for e in events if e['event'] == 'transport']) == len(schedule['transports'])
    assert len([e for e in events if e['event'] == 'care']) == len(schedule['care'])
    assert all(e['record_only'] for e in events if e['event'] in ('transport', 'care', 'operation_continue'))
    assert [e['time_min'] for e in events] == sorted(e['time_min'] for e in events)


@pytest.mark.parametrize('arrival', [0.0, 10.0, 20.0])
def test_clock_conversion_includes_prelude_and_delayed_arrivals(arrival):
    assert timeline.injury_time_s(arrival + 2, arrival) == 120
    assert timeline.native_time_s(arrival + 2, arrival) == 180
    assert timeline.global_time_min(180, arrival) == arrival + 2
    assert timeline.injury_time_s(arrival, arrival) == 0


def record(pid='P01'):
    return {'patient_id': pid, 'arrival_time_min': 0.0,
            'samples': [{'time_min': float(t), 'CardiacOutput_L_min': float(co),
                         'MAP_mmHg': 80.0, 'BloodVolume_mL': 4800.0} for t, co in [(0, 2), (1, 4), (2, 6)]],
            'events': [], 'actions': [], 'reached_horizon': True, 'terminal_event': None,
            'engine_failure': None, 'injury_unsupported': None, 'treatment_incomplete': False,
            'exploratory': False}


@pytest.mark.parametrize('window', ['complete', 'complete_terminal', 'incomplete_engine_failure', 'not_simulated'])
def test_four_window_integral_rules(window):
    value = record()
    horizon = 2.0
    if window == 'complete_terminal':
        value.update(terminal_event={'event': 'IrreversibleState', 'time_min': 2.0}, reached_horizon=False)
        horizon = 120.0
    elif window == 'incomplete_engine_failure':
        value.update(engine_failure={'code': 'NATIVE_ADVANCE_FAILED'}, reached_horizon=False)
    elif window == 'not_simulated':
        value.update(injury_unsupported={'status': 'INJURY_UNSUPPORTED', 'detail': 'test'}, reached_horizon=False, samples=[])
    result = outcomes.patient_outcome(value, horizon)
    assert result['window_status'] == window
    assert result['observed_integral_CO_L'] == (None if window == 'not_simulated' else 8.0)
    assert result['integral_CO_L'] == (8.0 if window in ('complete', 'complete_terminal') else None)
    assert result['final_MAP_mmHg'] == (80.0 if window == 'complete' else None)
    assert result['final_BloodVolume_mL'] == (4800.0 if window == 'complete' else None)


def test_integral_clips_terminal_trapezoid_and_handles_duplicate_action_samples():
    rows = record()['samples']
    rows.insert(2, copy.deepcopy(rows[1]))
    assert outcomes.trapezoid(rows, 0, 1.5) == 5.25
    assert outcomes.trapezoid(rows, 0, 120) == 8.0  # no extrapolation beyond samples


def test_observed_integral_and_terminal_window_integral_remain_distinct():
    value = record()
    value.update(terminal_event={'event': 'CardiacArrest', 'time_min': 1.5}, reached_horizon=False)
    result = outcomes.patient_outcome(value)
    assert result['observed_integral_CO_L'] == 8.0  # all valid samples up to last observed time
    assert result['integral_CO_L'] == 5.25  # full window cuts off at the event; zero thereafter


def test_terminal_event_is_not_counted_as_engine_failure():
    value = record()
    value.update(terminal_event={'event': 'CardiacArrest', 'time_min': 2.0}, engine_failure={'code': 'same_step_failed'})
    result = outcomes.evaluate({'P01': value})
    assert result['patients']['P01']['window_status'] == 'complete_terminal'
    assert result['summary']['engine_failures'] == 0
    assert result['summary']['deaths'] == 1


def test_summary_denominators_exclusions_flags_and_shock():
    records = {f'P{i:02}': record(f'P{i:02}') for i in range(1, 7)}
    records['P02'].update(terminal_event={'event': 'CardiacArrest', 'time_min': 2.0}, reached_horizon=False)
    records['P03'].update(engine_failure={'code': 'failed'}, reached_horizon=False)
    records['P04'].update(injury_unsupported={'detail': 'missing adapter'}, samples=[], reached_horizon=False)
    records['P05'].update(treatment_incomplete=True, actions=[
        {'action_id': 'a', 'status': 'ACTION_UNSUPPORTED', 'reason': {'detail': 'unsupported'}}])
    records['P06'].update(exploratory=True, events=[
        {'event': 'HypovolemicShock', 'active': True, 'time_min': 1.0},
        {'event': 'HypovolemicShock', 'active': False, 'time_min': 1.5},
        {'event': 'HypovolemicShock', 'active': True, 'time_min': 1.8}])
    result = outcomes.evaluate(records, 2.0)
    assert result['patients']['P06']['first_hypovolemic_shock_min'] == 1.0
    assert result['summary']['window_status_counts'] == {
        'complete': 3, 'complete_terminal': 1, 'incomplete_engine_failure': 1, 'not_simulated': 1}
    all_available, clean = result['summary']['all_available'], result['summary']['clean']
    assert (all_available['total_CO_L'], all_available['mean_CO_L'], all_available['denominator']) == (32, 8, 4)
    assert all_available['excluded_patients'] == [
        {'patient_id': 'P03', 'reasons': ['incomplete_engine_failure']},
        {'patient_id': 'P04', 'reasons': ['not_simulated']}]
    assert (clean['total_CO_L'], clean['mean_CO_L'], clean['denominator']) == (16, 8, 2)
    assert clean['excluded_patients'][-2:] == [
        {'patient_id': 'P05', 'reasons': ['treatment_incomplete']},
        {'patient_id': 'P06', 'reasons': ['exploratory']}]


def test_empty_available_population_has_no_mean():
    value = record()
    value.update(injury_unsupported={'detail': 'unsupported'}, samples=[])
    result = outcomes.evaluate({'P01': value})['summary']['all_available']
    assert result['denominator'] == 0 and result['mean_CO_L'] is None


def test_no_realtime_pacing_or_tick_loop():
    directory = Path(timeline.__file__).parent
    for path in directory.rglob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
                assert name not in ('sleep', 'advance_timestep', 'advance_step'), (path, node.lineno, name)
