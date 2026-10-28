import asyncio
import copy
import hashlib
import json

import pytest

from core301.agent_chain.bridge import execute_patient
from core301.agent_chain.graph import build_graph
from core301.agent_chain.nodes import Providers
from core301.agent_chain.runner import run_chain
from core301.agent_chain.scheduling import FakeSchedulingProvider
from core301.agent_chain.treatment import FakeTreatmentProvider, template_decisions
from core301.dispatch.minimal import api


def fast_execute(cases, timeline, run_dir, *, native, horizon_min, dataset_dir=api.DATASET):
    assert not native
    specs = {s['patient_id']: s for s in api.read(dataset_dir / 'patient_specs.json')}
    return {c['patient_id']: execute_patient(specs[c['patient_id']], timeline,
            run_dir / 'execution' / c['patient_id'], horizon_min=horizon_min, native=False) for c in cases}


def run(tmp_path, responses, *, treatment=None, attempts=3):
    scheduling = FakeSchedulingProvider(responses)
    providers = Providers(treatment or FakeTreatmentProvider(template_decisions()), scheduling, fast_execute)
    summary = asyncio.run(run_chain('offline', 'run', max_schedule_attempts=attempts,
                                    root=tmp_path, providers=providers))
    return summary, scheduling, tmp_path / 'run'


def withdraw(schedule, pid, reason='no_feasible_schedule_found'):
    result = copy.deepcopy(schedule)
    result['selections'].pop(pid)
    for category in ('operations', 'transports', 'care'):
        result[category] = [t for t in result[category] if t['patient_id'] != pid]
    row = next(p for p in result['patient_results'] if p['patient_id'] == pid)
    row.update(status='unscheduled', reason_code=reason,
               reason='The provider has not completed verification of all treatment alternatives.',
               considered_alternatives=['Reviewed the treatment alternatives but did not complete all checks.'])
    return result


def test_graph_nodes_and_all_three_validation_edges(chain_data):
    _, _, _, schedule = chain_data
    graph = build_graph(Providers(FakeTreatmentProvider(template_decisions()),
                                  FakeSchedulingProvider([schedule]), fast_execute), {'max_schedule_attempts': 3})
    structure = graph.get_graph()
    assert set(structure.nodes) == {'__start__', '__end__', 'load_scenario', 'treatment',
        'build_dispatch_input', 'schedule', 'validate', 'build_timeline', 'execute', 'evaluate'}
    assert {e.target for e in structure.edges if e.source == 'validate' and e.conditional} == {
        'schedule', 'build_timeline', '__end__'}
    assert not any((e.source, e.target) in (('schedule', 'treatment'), ('execute', 'treatment')) for e in structure.edges)


def test_success_snapshots_and_audit_digests(chain_data, tmp_path):
    _, _, context, schedule = chain_data
    summary, provider, directory = run(tmp_path, [schedule])
    assert summary['status'] == 'completed' and summary['execution_patients'] == 16
    assert summary['treatment_stage'] == 'ok' and summary['schedule_stage'] == 'full'
    assert summary['schedule_attempts'] == 1 and summary['accepted_patients'] == 16
    assert provider.calls[0]['feedback'] is None and provider.calls[0]['previous_response'] is None
    loaded = api.read(directory / 'state/load_scenario.json')
    assert all('candidate_plans' not in c for c in loaded['cases'])
    assert api.read(directory / 'dispatch_input.json') == context
    assert len(list((directory / 'state').glob('*.json'))) == 8
    digests = api.read(directory / 'sha256_manifest.json')
    assert 'summary.json' in digests and 'sha256_manifest.json' not in digests
    for name, digest in digests.items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    before = len(provider.calls)
    with pytest.raises(FileExistsError):
        asyncio.run(run_chain('offline', 'run', root=tmp_path,
                    providers=Providers(FakeTreatmentProvider(template_decisions()), provider, fast_execute)))
    assert len(provider.calls) == before


def test_conflict_retry_carries_raw_response_history_and_withdrawal(chain_data, tmp_path):
    _, _, _, good = chain_data
    bad = copy.deepcopy(good)
    bad['operations'][0]['staff_ids'] = ['invalid-staff']
    partial = withdraw(good, 'P01')
    summary, provider, directory = run(tmp_path, [bad, partial, good])
    assert summary['status'] == 'completed' and len(provider.calls) == 3
    assert provider.calls[1]['previous_response'] == json.dumps(bad)
    assert provider.calls[1]['feedback']['conflicts']
    latest = provider.calls[2]['feedback']
    assert latest['conflicts'] == []
    assert latest['withdrawn_this_round'][0]['patient_id'] == 'P01'
    assert any(c['current_status'] == 'not_triggered_after_withdrawal' for c in latest['historical_conflicts'])
    state = api.read(directory / 'state/validate.json')
    assert state['schedule_attempts'][1]['best_passed_attempt'] == 2
    assert state['schedule_attempts'][2]['best_passed_attempt'] == 3
    assert state['accepted_schedule'] == good


@pytest.mark.parametrize('attempts', [2, 3])
def test_conflicts_at_attempt_limit_execute_everyone_without_treatment(chain_data, tmp_path, attempts):
    _, _, _, bad = chain_data
    bad['operations'][0]['end_min'] = 1.0
    summary, provider, directory = run(tmp_path, [bad], attempts=attempts)
    assert summary['status'] == 'completed' and len(provider.calls) == attempts
    assert summary['schedule_stage'] == 'failed' and summary['execution_patients'] == 16
    events = api.read(directory / 'timeline.json')
    assert len(events) == 16 and all(e['event'] == 'injury_onset' for e in events)
    assert {e['treatment_status'] for e in events} == {'no_schedule'}


@pytest.mark.parametrize('reason,calls', [('missing_parameters', 1), ('no_feasible_schedule_found', 2)])
def test_missing_parameters_accept_immediately_other_omissions_wait_for_limit(chain_data, tmp_path, reason, calls):
    _, _, _, good = chain_data
    summary, provider, directory = run(tmp_path, [withdraw(good, 'P01', reason)], attempts=2)
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'partial'
    assert len(provider.calls) == calls and summary['execution_patients'] == 16
    state = api.read(directory / 'state/validate.json')
    assert not state['validation']['conflicts']
    assert state['schedule_attempts'][-1]['best_passed_attempt'] == 1  # preserve first on ties


def test_provider_validation_disagreement_stops_immediately(chain_data, tmp_path):
    _, _, _, good = chain_data
    proposal = {'schedule': good, 'raw_response': json.dumps(good), 'metadata': {},
                'validation': {'conflicts': [], 'fabricated': True}}
    summary, provider, directory = run(tmp_path, [proposal])
    assert summary['status'] == 'aborted' and len(provider.calls) == 1
    assert summary['schedule_stage'] == 'aborted' and summary['treatment_stage'] == 'ok'
    assert summary['outcomes'] is None and not (directory / 'outcomes.json').exists()
    assert api.read(directory / 'schedule/attempt_01/error.json')['code'] == 'PROVIDER_VALIDATION_MISMATCH'
    assert not api.read(directory / 'schedule/attempt_01/validation.json')['conflicts']
    assert not (directory / 'timeline.json').exists()


def test_demonstration_flag_is_required(chain_data, tmp_path):
    _, _, _, bad = chain_data
    # Remove selected actions so the separate demonstration flag check is reached,
    # rather than the validator already rejecting unconfirmed action eligibility.
    for pid in list(bad['selections']):
        bad = withdraw(bad, pid, 'missing_parameters')
    bad['demonstration_only'] = False
    summary, _, directory = run(tmp_path, [bad], attempts=1)
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'failed'
    conflicts = api.read(directory / 'schedule/attempt_01/validation.json')['conflicts']
    assert any(c['code'] == 'DEMONSTRATION_FLAG_REQUIRED' for c in conflicts)


def test_request_exception_is_not_retried_or_leaked(tmp_path):
    summary, provider, directory = run(tmp_path, [RuntimeError('secret-credential')])
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'failed'
    assert len(provider.calls) == 1 and summary['execution_patients'] == 16
    assert summary['schedule_error'] == {'code': 'SCHEDULE_REQUEST_FAILED', 'attempt': 1,
                                         'error_type': 'RuntimeError', 'status_code': None}
    assert 'secret-credential' not in ''.join(p.read_text() for p in directory.rglob('*.json'))


@pytest.mark.parametrize('candidate', [None, {'selections': None}, {'selections': [['invalid']]}, {}])
def test_invalid_schedule_shape_still_produces_bounded_feedback(tmp_path, candidate):
    response = {'schedule': candidate, 'raw_response': json.dumps(candidate), 'metadata': {}}
    summary, provider, _ = run(tmp_path, [response], attempts=2)
    assert summary['status'] == 'completed' and summary['schedule_stage'] == 'failed'
    assert len(provider.calls) == 2
    assert provider.calls[1]['feedback']['conflicts'][0]['code'] == 'SCHEMA_INVALID'


def test_treatment_failure_excludes_patient_without_template_fallback(chain_data, tmp_path):
    _, _, _, schedule = chain_data
    responses = template_decisions()
    responses['P01'] = RuntimeError('secret-credential')
    summary, _, directory = run(tmp_path, [schedule], treatment=FakeTreatmentProvider(responses), attempts=1)
    assert summary['excluded_patients'] == {
        'P01': {'reason_code': 'CALL_FAILED', 'error_type': 'RuntimeError', 'status_code': None}}
    assert len(api.read(directory / 'dispatch_input.json')['patients']) == 15
    assert 'P01' not in {p['patient_id'] for p in api.read(directory / 'dispatch_input.json')['patients']}
    assert 'secret-credential' not in (directory / 'treatment/P01/admission.json').read_text()


def test_all_treatment_failures_skip_schedule_but_execute_everyone(tmp_path):
    treatment = FakeTreatmentProvider({pid: '{invalid' for pid in template_decisions()})
    summary, provider, directory = run(tmp_path, [{}], treatment=treatment)
    assert summary['status'] == 'completed' and provider.calls == []
    assert summary['treatment_stage'] == 'failed' and summary['schedule_stage'] == 'skipped'
    assert summary['execution_patients'] == 16
    assert summary['outcomes']['treatment_status_counts']['treatment_excluded'] == 16
    assert len(summary['excluded_patients']) == 16
    assert not (directory / 'dispatch_input.json').exists()


@pytest.mark.parametrize('attempts', [0, 6, True])
def test_attempt_bounds_are_enforced_before_run_directory(tmp_path, attempts):
    with pytest.raises(ValueError):
        asyncio.run(run_chain('offline', 'bad', root=tmp_path, max_schedule_attempts=attempts))
    assert not (tmp_path / 'bad').exists()
