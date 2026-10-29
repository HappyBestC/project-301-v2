import json

from core301.standard_answer import cli
from core301.standard_answer.scenario import load_scenario
from core301.dispatch.minimal import api
from core301.agent_chain import bridge
from tests.standard_answer.helpers import write_fake_tables, table_text
from tests.standard_answer.test_optimality import tiny_context


def _forbid_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('solve must not execute Pulse or request an LLM')
    monkeypatch.setattr(bridge, 'execute_all', forbidden)
    monkeypatch.setattr(bridge, 'execute_patient', forbidden)
    monkeypatch.setattr(api, 'request_agent_schedule', forbidden)


def test_run002_fake_tables_end_to_end_without_pulse_or_llm(tmp_path, monkeypatch):
    _forbid_calls(monkeypatch)
    tables = write_fake_tables(tmp_path / 'tables', delay_dependent=True)
    monkeypatch.setattr(cli, 'PROJECT_ROOT', tmp_path)
    assert cli.main(['solve', '--tables', str(tables), '--run-id', 'e2e', '--time-limit-s', '60', '--workers', '2']) == 0
    run = tmp_path / 'runs/standard_answer/e2e'
    read = lambda name: json.loads((run / name).read_text())
    assert read('validation.json')['conflicts'] == []
    assert len(read('schedule.json')['patient_results']) == 16
    assert len(read('prediction.json')['patients']) == 16
    assert read('solve.json')['parameters']['max_followup_gap'] == 0
    assert len(read('solve.json')['stages']) == 3
    assert not (run / 'pulse').exists()


def test_typical_mode_optimizes_base_but_evaluates_true_variant(tmp_path, monkeypatch):
    _forbid_calls(monkeypatch)
    context = tiny_context(1)
    _, specs, base, _ = load_scenario({'base': 'run_002', 'overrides': {'P05': {'severity': .8}}})
    definition = {'base': 'run_002', 'overrides': {'P05': {'severity': .8}}}
    monkeypatch.setattr(cli, 'load_scenario', lambda _: (context, specs, base, definition))
    monkeypatch.setattr(cli, 'PROJECT_ROOT', tmp_path)
    tables = write_fake_tables(tmp_path / 'tables', context, base)
    write_fake_tables(tables, context, specs)
    for path in tables.glob('*s0.8*.csv'):
        summary, cumulative = table_text([('untreated', None, 5, 'run', 'complete')] +
            [(d, None, 2, 'run', 'complete') for d in range(121)])
        path.write_text(cumulative if '__cum_deficit_L' in path.name else summary)
    assert cli.main(['solve', '--table-mode', 'typical', '--tables', str(tables), '--run-id', 'typical',
                     '--time-limit-s', '10', '--workers', '1']) == 0
    run = tmp_path / 'runs/standard_answer/typical'
    result = json.loads((run / 'solve.json').read_text())
    prediction = json.loads((run / 'prediction.json').read_text())
    assert result['objective']['deficit10'] == 0
    assert prediction['deficit10'] == 2400
    assert 's0.8' in prediction['patients'][0]['table']


def test_missing_true_table_is_not_replaced_by_typical(tmp_path, monkeypatch):
    context = tiny_context(1)
    _, specs, base, definition = load_scenario({'base': 'run_002', 'overrides': {'P05': {'severity': .8}}})
    monkeypatch.setattr(cli, 'load_scenario', lambda _: (context, specs, base, definition))
    monkeypatch.setattr(cli, 'PROJECT_ROOT', tmp_path)
    tables = write_fake_tables(tmp_path / 'tables', context, base)
    assert cli.main(['solve', '--table-mode', 'typical', '--tables', str(tables), '--run-id', 'missing']) == 2
    assert not (tmp_path / 'runs/standard_answer/missing').exists()
