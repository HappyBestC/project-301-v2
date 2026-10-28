import json
import sys

import pytest

from core301.agent_chain import nodes, runner
from core301.agent_chain.treatment import FakeTreatmentProvider, template_decisions
from core301.dispatch.minimal import api
from tests.agent_chain.test_graph import run, withdraw


def partial(schedule, omissions):
    result = schedule
    for pid in omissions:
        result = withdraw(result, pid)
    return result


@pytest.mark.parametrize('counts,expected', [((12, 14, 13), 2), ((14, 14, 12), 1)])
def test_partial_coverage_selects_largest_and_earliest(chain_data, tmp_path, counts, expected):
    _, _, _, schedule = chain_data
    safe = ['P01', 'P04', 'P05', 'P08', 'P09', 'P10', 'P12', 'P14']
    proposals = [partial(schedule, safe[i:i + 16 - count]) for i, count in enumerate(counts)]
    summary, provider, directory = run(tmp_path, proposals)
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'partial'
    assert len(provider.calls) == 3 and summary['accepted_patients'] == max(counts)
    assert api.read(directory / 'schedule.json') == proposals[expected - 1]
    state = api.read(directory / 'state/validate.json')
    assert all(not a['validation']['conflicts'] for a in state['schedule_attempts'])
    assert state['schedule_attempts'][-1]['best_passed_attempt'] == expected
    actual = api.read(directory / 'outcomes.json')
    for row in proposals[expected - 1]['patient_results']:
        patient = actual['patients'][row['patient_id']]
        if row['status'] == 'unscheduled':
            assert patient['unscheduled_reason_code'] == row['reason_code']
            assert patient['unscheduled_reason'] == row['reason']
    assert summary['outcomes']['all_available']['denominator'] == 16
    assert summary['outcomes']['clean']['denominator'] == 14


def test_request_failure_uses_prior_partial_without_another_call(chain_data, tmp_path):
    _, _, _, schedule = chain_data
    candidate = withdraw(schedule, 'P01')
    summary, provider, directory = run(tmp_path, [candidate, TimeoutError('secret request body'), schedule])
    assert len(provider.calls) == 2 and summary['schedule_stage'] == 'partial'
    assert summary['status'] == 'completed' and summary['execution_patients'] == 16
    assert api.read(directory / 'schedule.json') == candidate
    assert summary['schedule_error'] == {'code': 'SCHEDULE_REQUEST_FAILED', 'attempt': 2,
                                         'error_type': 'TimeoutError', 'status_code': None}
    assert 'secret request body' not in json.dumps(api.read(directory / 'summary.json'))


def test_scheduled_unscheduled_and_excluded_patients_all_execute(chain_data, tmp_path):
    _, _, _, schedule = chain_data
    # P01 never enters dispatch. P04 enters, but no candidate round includes it.
    schedule = withdraw(schedule, 'P01')
    schedule['patient_results'] = [r for r in schedule['patient_results'] if r['patient_id'] != 'P01']
    schedule = withdraw(schedule, 'P04')
    responses = template_decisions()
    responses['P01'] = '{broken'
    summary, _, directory = run(tmp_path, [schedule], treatment=FakeTreatmentProvider(responses))
    assert summary['treatment_stage'] == 'partial' and summary['schedule_stage'] == 'partial'
    assert summary['execution_patients'] == 16
    result = api.read(directory / 'outcomes.json')
    assert result['summary']['treatment_status_counts'] == {
        'scheduled': 14, 'unscheduled': 1, 'treatment_excluded': 1, 'no_schedule': 0}
    assert result['patients']['P01']['treatment_exclusion_reason'] == summary['excluded_patients']['P01']
    assert result['patients']['P04']['unscheduled_reason_code'] == 'no_feasible_schedule_found'
    assert len(api.read(directory / 'dispatch_input.json')['patients']) == 15
    events = api.read(directory / 'timeline.json')
    for pid in ('P01', 'P04'):
        own = [e for e in events if e['patient_id'] == pid]
        assert len(own) == 1 and own[0]['event'] == 'injury_onset'
        record = api.read(directory / 'execution' / pid / 'execution.json')
        assert record['reached_horizon'] and not record['treatment_incomplete']
        assert api.read(directory / 'execution' / pid / 'actions.json') == []
    assert result['summary']['all_available']['denominator'] == 16
    assert result['summary']['clean']['denominator'] == 14


def test_no_treatment_needed_is_scheduled_empty_plan(chain_data, tmp_path):
    _, _, _, schedule = chain_data
    responses = template_decisions()
    decision = json.loads(responses['P01'])
    decision.update(decision_type='no_treatment_needed', candidate_plans=[], refusal_reason='Test empty plan')
    responses['P01'] = json.dumps(decision)
    for category in ('operations', 'care', 'transports'):
        schedule[category] = [task for task in schedule[category] if task['patient_id'] != 'P01']
    summary, provider, directory = run(tmp_path, [schedule], treatment=FakeTreatmentProvider(responses))
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'full'
    assert len(provider.calls) == 1
    result = api.read(directory / 'outcomes.json')['patients']['P01']
    assert result['treatment_status'] == 'scheduled' and result['injected_actions'] == 0


@pytest.mark.parametrize('phase,expected_treatment,expected_schedule', [
    ('load', 'not_reached', 'not_reached'), ('treatment', 'aborted', 'not_reached'),
    ('validate', 'ok', 'aborted'), ('execute', 'ok', 'full')])
def test_unexpected_abort_records_exact_stage_progress(chain_data, tmp_path, monkeypatch,
                                                       phase, expected_treatment, expected_schedule):
    def fail(*args, **kwargs):
        raise RuntimeError('secret-exception-detail')
    if phase == 'load':
        monkeypatch.setattr(nodes.Nodes, 'load_scenario', fail)
    elif phase == 'treatment':
        original = nodes.build_treatment_input
        def fail_second(case, mapping):
            return fail() if case['patient_id'] == 'P02' else original(case, mapping)
        monkeypatch.setattr(nodes, 'build_treatment_input', fail_second)
    elif phase == 'validate':
        monkeypatch.setattr(nodes, 'independently_validate', fail)
    elif phase == 'execute':
        monkeypatch.setattr(nodes.Nodes, 'execute', fail)
    _, _, _, schedule = chain_data
    summary, provider, directory = run(tmp_path, [schedule])
    assert summary['status'] == 'aborted' and summary['outcomes'] is None
    assert summary['treatment_stage'] == expected_treatment
    assert summary['schedule_stage'] == expected_schedule
    assert not (directory / 'outcomes.json').exists()
    assert 'secret-exception-detail' not in ''.join(p.read_text() for p in directory.rglob('*.json'))
    if phase in ('load', 'treatment'):
        assert not provider.calls


@pytest.mark.parametrize('status,exit_code', [('completed', 0), ('execution_partial', 0), ('aborted', 1)])
def test_cli_exit_status_and_token_parameter(monkeypatch, capsys, status, exit_code):
    received = []
    async def capture(*args, **kwargs):
        received.append(kwargs)
        return {'status': status}
    monkeypatch.setattr(runner, 'run_chain', capture)
    monkeypatch.setattr(sys, 'argv', ['runner', '--mode', 'offline', '--run-id', 'test',
                                    '--treatment-max-tokens', '4096'])
    assert runner.main() == exit_code
    assert received[0]['treatment_max_tokens'] == 4096
    assert json.loads(capsys.readouterr().out)['status'] == status


def test_live_provider_construction_passes_token_parameter_without_calling_models(monkeypatch):
    received = []
    monkeypatch.setattr(runner, 'LLMTreatmentProvider', lambda value: received.append(value) or object())
    monkeypatch.setattr(runner, 'LLMSchedulingProvider', object)
    runner.mode_providers('live', treatment_max_tokens=4096)
    assert received == [4096]
