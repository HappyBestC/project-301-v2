import hashlib

import pytest

from core301.agent_chain.audit import write_json
from core301.standard_answer import compare
from core301.standard_answer.scenario import load_scenario


def samples(path, arrival, co):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'time_min,CardiacOutput_L_min\n{arrival},{co}\n120,{co}\n')


def execution(directory, patients, co, death=False):
    for p in patients:
        folder = directory / 'execution' / p['patient_id']
        samples(folder / 'samples.csv', p['arrival_time_min'], co)
        write_json(folder / 'execution.json', dict(arrival_time_min=p['arrival_time_min'], reached_horizon=True,
            terminal_event={'time_min': 60} if death and p['patient_id'] == 'P01' else None))


@pytest.fixture
def experiment(tmp_path):
    context, *_ = load_scenario()
    patients = context['patients']
    reference_dir = tmp_path / 'reference'
    samples(reference_dir / 'samples.csv', 0, 5)
    untreated = tmp_path / 'untreated'
    execution(untreated, patients, 4, death=True)
    expected = [{'patient_id': p['patient_id'], 'death': int(p['patient_id'] == 'P01'),
        'terminal_global_min': 60 if p['patient_id'] == 'P01' else None,
        'deficit_L': 362 if p['patient_id'] == 'P01' else 120 - p['arrival_time_min']} for p in patients]
    baseline = tmp_path / 'baseline.json'
    write_json(baseline, dict(patients=expected, deaths=1, deficit_L=sum(p['deficit_L'] for p in expected),
        reference_sha256=hashlib.sha256((reference_dir / 'samples.csv').read_bytes()).hexdigest()))
    schedule = dict(selections={'P01': patients[0]['candidate_plans'][0]['plan_id']}, operations=[
        dict(patient_id='P01', action_id=patients[0]['candidate_plans'][0]['actions'][0]['action_id'], mode='start', end_min=12)])
    runs = []
    for name, group, accepted in [('failed', 'L0', False), ('accepted', 'L0', True), ('L1', 'L1', True)]:
        directory = tmp_path / name
        write_json(directory / 'manifest.json', dict(mode='live_schedule', scenario='run_002', parameters=dict(schedule_variant=group)))
        chosen = schedule if accepted else None
        attempts = [dict(attempt=1, candidate=schedule, validation={'conflicts': [] if accepted else [{'code': 'X'}]},
            metadata={'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}, 'model_elapsed_s': 2.5})]
        write_json(directory / 'state/validate.json', dict(accepted_schedule=chosen, schedule_attempts=attempts))
        if accepted:
            execution(directory, patients, 5)
        # Failed run deliberately has no execution: it must still contribute all untreated patients.
        runs.append(directory)
    standards = []
    for label in ('G0', 'G60'):
        directory = tmp_path / label
        write_json(directory / 'schedule.json', schedule)
        execution(directory / 'pulse', patients, 5)
        standards.append(directory)
    return dict(runs=runs, standards=standards, out=tmp_path / 'out', untreated_run=untreated,
                reference_dir=reference_dir, baseline=baseline)


def test_comparison_counts_failures_controls_and_patient_delays(experiment):
    rows, controls, details = compare.compare_runs(**experiment)
    expected_deficit = compare.read(experiment['baseline'])['deficit_L']
    assert rows[0]['pulse_deaths'] == 1 and rows[0]['co_deficit_L'] == expected_deficit
    assert rows[0]['scheduled_patients'] == 0 and rows[0]['accepted_attempt'] is None
    assert rows[1]['co_deficit_L'] == 0 and rows[1]['accepted_attempt'] == 1
    assert rows[1]['total_tokens'] == 30 and rows[1]['model_elapsed_s'] == 2.5
    assert len(details) == 16 * 6
    assert [c['pulse_deaths'] for c in controls] == [1, 0, 0]
    assert next(d for d in details if d['patient_id'] == 'P01' and d['run_id'] == 'accepted')['effective_after_injury_min'] == 12
    summary = (experiment['out'] / 'summary.md').read_text()
    assert '| L0 | 2 | 50.00% | 0.50 / 0.00 / 1.00 |' in summary
    assert '| L1 | 1 | 100.00%' in summary
    assert len(compare.csv_rows(experiment['out'] / 'comparison.csv')) == 6
    per_patient = compare.csv_rows(experiment['out'] / 'per_patient.csv')
    assert len(per_patient) == 16
    assert per_patient[0]['accepted.effective_after_injury_min'] == '12'
    assert per_patient[0]['G0.death'] == '0'
    assert per_patient[0]['untreated.death'] == '1'


def test_baseline_mismatch_fails_instead_of_silently_comparing(experiment):
    data = compare.read(experiment['baseline'])
    data['patients'][0]['deficit_L'] += 1
    write_json(experiment['baseline'], data)
    with pytest.raises(ValueError, match='baseline mismatch'):
        compare.compare_runs(**experiment)
    assert not experiment['out'].exists()


def test_incomplete_accepted_execution_is_not_dropped(experiment):
    folder = experiment['runs'][1] / 'execution/P01/execution.json'
    write_json(folder, dict(arrival_time_min=0, reached_horizon=False))
    with pytest.raises(ValueError, match='incomplete Pulse'):
        compare.compare_runs(**experiment)


def test_cli_resolves_quoted_run_glob_and_untreated(monkeypatch, tmp_path):
    (tmp_path / 'llm_L0_1').mkdir()
    (tmp_path / 'llm_L1_1').mkdir()
    monkeypatch.setattr(compare, 'RESULTS_ROOT', tmp_path)
    captured = []
    monkeypatch.setattr(compare, 'compare_runs', lambda *args, **kw: captured.append((args, kw)))
    assert compare.main(['--runs', 'llm_L*', '--standard', 'G0', 'G60', '--untreated-run', 'original', '--out', 'out']) == 0
    assert len(captured[0][0][0]) == 2
    assert str(captured[0][1]['untreated_run']) == 'original'
