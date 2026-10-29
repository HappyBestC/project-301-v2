import asyncio
import copy
import hashlib
import json

import pytest

from core301.agent_chain import baseline, runner, treatment
from core301.agent_chain.audit import write_json
from core301.agent_chain.nodes import Providers
from core301.agent_chain.scheduling import FakeSchedulingProvider
from core301.agent_chain.scenarios import scenario_paths
from core301.dispatch.minimal import api
from core301.standard_answer.scenario import load_scenario
from core301.standard_answer.tables import TableStore
from tests.agent_chain.test_graph import fast_execute
from tests.agent_chain.test_provider_audit import client_mock, scheduling_provider
from tests.standard_answer.helpers import write_fake_tables, table_text


def empty_schedule(reason='missing_parameters'):
    context, *_ = load_scenario()
    return dict(demonstration_only=True, selections={}, operations=[], transports=[], care=[],
        patient_results=[dict(patient_id=p['patient_id'], status='unscheduled', reason_code=reason,
            reason='Missing host parameters', blocking_resources=[], considered_alternatives=['Checked inputs'])
            for p in context['patients']])


def fake_native(cases, timeline, run_dir, *, native, **kwargs):
    assert native
    return fast_execute(cases, timeline, run_dir, native=False, **kwargs)


@pytest.mark.parametrize('variant', ['L0', 'L1'])
def test_live_schedule_templates_model_copy_and_existing_acceptance(tmp_path, monkeypatch, variant):
    tables = write_fake_tables(tmp_path / 'tables', delay_dependent=True) if variant == 'L1' else None
    class ForbiddenTreatment(treatment.LLMTreatmentProvider):
        def __init__(self, *args, **kwargs):
            raise AssertionError('Treatment model must not be constructed')
    monkeypatch.setattr(runner, 'LLMTreatmentProvider', ForbiddenTreatment)
    scheduling = FakeSchedulingProvider([empty_schedule()])
    monkeypatch.setattr(runner, 'LLMSchedulingProvider', lambda **kw: scheduling)
    providers = runner.mode_providers('live_schedule', 'run_002', schedule_variant=variant)
    assert isinstance(providers.treatment, treatment.TemplateTreatmentProvider)
    providers.execute = fake_native
    result = asyncio.run(runner.run_chain('live_schedule', 'test', root=tmp_path,
        scenario='run_002', schedule_variant=variant, tables=tables, providers=providers))
    assert result['status'] == 'completed'
    assert result['treatment_stage'] == 'ok' and result['execution_patients'] == 16
    assert len(scheduling.calls) == 1  # V1.2 missing_parameters exception is retained.
    assert all(('urgency' in p) == (variant == 'L1') for p in scheduling.calls[0]['dispatch_input']['patients'])
    context = api.read(tmp_path / 'test/dispatch_input.json')
    assert all('urgency' not in p for p in context['patients'])
    assert context['patients'] == load_scenario()[0]['patients']
    parameters = api.read(tmp_path / 'test/manifest.json')['parameters']
    assert parameters['schedule_variant'] == variant
    assert parameters['prompt_sha256'] == hashlib.sha256(baseline.prompt_path(variant).read_bytes()).hexdigest()
    assert parameters['tables_sha256'] == (TableStore(tables).hashes if tables else {})
    assert api.read(tmp_path / 'test/schedule/attempt_01/request.json')['dispatch_input'] == scheduling.calls[0]['dispatch_input']


@pytest.mark.parametrize('reason,count', [('missing_parameters', 1), ('no_feasible_schedule_found', 3)])
def test_live_schedule_reuses_retry_and_acceptance(tmp_path, reason, count):
    scheduler = FakeSchedulingProvider([empty_schedule(reason)])
    providers = Providers(treatment.TemplateTreatmentProvider(scenario_paths('run_002')['dataset_dir']), scheduler, fake_native)
    result = asyncio.run(runner.run_chain('live_schedule', 'test', root=tmp_path,
        scenario='run_002', providers=providers))
    assert len(scheduler.calls) == count
    assert result['schedule_stage'] == 'partial'


def test_three_conflicting_rounds_execute_everyone_untreated(tmp_path):
    scheduler = FakeSchedulingProvider([{}])
    providers = Providers(treatment.TemplateTreatmentProvider(scenario_paths('run_002')['dataset_dir']), scheduler, fake_native)
    result = asyncio.run(runner.run_chain('live_schedule', 'test', root=tmp_path, scenario='run_002', providers=providers))
    assert result['schedule_stage'] == 'failed' and len(scheduler.calls) == 3
    assert result['execution_patients'] == 16
    assert all(e['event'] == 'injury_onset' for e in api.read(tmp_path / 'test/timeline.json'))


def test_urgency_matches_each_table_point_and_window(tmp_path):
    context, _, specs, _ = load_scenario()
    original = copy.deepcopy(context)
    tables = write_fake_tables(tmp_path / 'tables', delay_dependent=True)
    summary, cumulative = table_text([('untreated', 73.04, 2.123, 'run', 'complete_terminal'),
        (0, None, 0, 'run', 'complete'), (60, None, 0.567, 'run', 'complete'),
        (120, 110.04, 1.234, 'run', 'complete_terminal')])
    for path in tables.iterdir():
        path.write_text(cumulative if '__cum_deficit_L' in path.name else summary)
    store = TableStore(tables)
    result = baseline.with_urgency(context, tables)
    assert context == original
    for patient in result['patients']:
        window = 120 - int(patient['arrival_time_min'])
        for plan in patient['candidate_plans']:
            table = store.table(specs[patient['patient_id']], plan)
            info = patient['urgency']['plans'][plan['plan_id']]['effective_after_injury_min']
            assert set(info) == {str(d) for d in baseline.DELAYS if d <= window}
            for delay, value in info.items():
                cost = table.cost(int(delay), window)
                assert value == {'death': bool(cost.death), 'co_deficit_L': round(cost.deficit_L, 1)}
            assert patient['urgency']['untreated'] == {'terminal_event_after_injury_min': 73.0,
                'co_deficit_L': round(table.cost('untreated', window).deficit_L, 1)}


def test_objective_prompt_changes_only_target_paragraph():
    old = baseline.prompt_path('L0').read_bytes()
    new = baseline.prompt_path('L1').read_bytes()
    target = old.index('你的目标'.encode())
    end = old.index(b'\n\n')
    spec = (baseline.PROJECT_ROOT / 'docs/LLM_BASELINE_V1_DEV_SPEC.md').read_text()
    replacement = next(line[2:] for line in spec.splitlines() if line.startswith('> 你的目标')).encode()
    assert new == old[:target] + replacement + old[end:]


@pytest.mark.parametrize('code', sorted(baseline.HINT_CODES))
def test_resource_hints_real_local_matching_not_availability(code):
    context, *_ = load_scenario()
    patient = next(p for p in context['patients'] if p['patient_id'] == 'P05')
    action = patient['candidate_plans'][0]['actions'][0]
    rule = api.requirement(context['action_mapping'], action)
    operation = dict(task_id='bad', action_id=action['action_id'], location='H1', mode='start', access_mode='new')
    # Busy/late assets remain eligible as identity hints.
    for asset in context['resources']['personnel']:
        asset.update(status='unavailable', available_from_min=999)
    feedback = {'conflicts': [{'code': code, 'task_id': 'bad'}]}
    result = baseline.resource_hints(context, {'operations': [operation]}, feedback)
    assert 'valid_resource_hints' not in feedback['conflicts'][0]
    hints = result['conflicts'][0]['valid_resource_hints']
    for category in ('personnel', 'equipment', 'spaces'):
        assets = {r['id']: r for r in context['resources'][category]}
        for rid in hints[category]:
            asset = assets[rid]
            assert asset['location'] == 'H1'
            if category == 'personnel':
                assert set(asset['capabilities']) & set(rule['staff_roles'])
            else:
                assert asset['type'] in (rule['equipment'] if category == 'equipment' else rule['space_types']['hospital'])
    assert hints['personnel']


@pytest.mark.parametrize('variant', ['L0', 'L1'])
def test_actual_prompt_and_sdk_audit_without_network(tmp_path, monkeypatch, variant):
    scheduler = scheduling_provider()
    scheduler.schedule_variant = variant
    calls, settings = client_mock(monkeypatch, json.dumps(empty_schedule()))
    context, *_ = load_scenario()
    result = asyncio.run(scheduler.propose(context, feedback=None, previous_response=None, audit_dir=tmp_path))
    assert calls[0]['messages'][0]['content'] == baseline.prompt_path(variant).read_text()
    assert result['metadata']['usage']['total_tokens'] == 30
    assert result['metadata']['model_elapsed_s'] >= 0
    assert settings[0]['max_retries'] == 0 and settings[0]['timeout'] == 180
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_invalid_configuration_fails_before_provider_or_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'mode_providers', lambda *a, **kw: pytest.fail('constructed provider'))
    with pytest.raises(ValueError, match='tables'):
        asyncio.run(runner.run_chain('live_schedule', 'bad', root=tmp_path, scenario='run_002', schedule_variant='L1'))
    with pytest.raises(ValueError, match='at most 3'):
        asyncio.run(runner.run_chain('live_schedule', 'bad', root=tmp_path, scenario='run_002', max_schedule_attempts=4))
    assert not (tmp_path / 'bad').exists()


def test_graph_delivers_resource_hints_on_retry(tmp_path):
    context, *_ = load_scenario()
    plan = context['patients'][0]['candidate_plans'][0]
    schedule = empty_schedule('no_feasible_schedule_found')
    schedule['selections']['P01'] = plan['plan_id']
    schedule['patient_results'][0].update(status='scheduled', reason_code=None)
    action = plan['actions'][0]
    rule = api.requirement(context['action_mapping'], action)
    schedule['operations'] = [dict(task_id='bad-person', patient_id='P01', plan_id=plan['plan_id'],
        action_id=action['action_id'], location='A', start_min=0, end_min=rule['duration_min'],
        staff_ids=['invented-person'], equipment_ids=[], space_id='A-treatment-1', consumables=rule['consumables'])]
    scheduler = FakeSchedulingProvider([schedule, empty_schedule()])
    providers = Providers(treatment.TemplateTreatmentProvider(scenario_paths('run_002')['dataset_dir']), scheduler, fake_native)
    result = asyncio.run(runner.run_chain('live_schedule', 'test', root=tmp_path, scenario='run_002', providers=providers))
    assert result['status'] == 'completed' and len(scheduler.calls) == 2
    errors = scheduler.calls[1]['feedback']['conflicts']
    error = next(e for e in errors if e['code'] == 'UNKNOWN_RESOURCE')
    assert error['valid_resource_hints']['personnel']
    assert 'invented-person' not in error['valid_resource_hints']['personnel']
    # Feedback annotations never contaminate the independent validation evidence.
    validation = api.read(tmp_path / 'test/schedule/attempt_01/validation.json')
    assert all('valid_resource_hints' not in c for c in validation['conflicts'])


def test_care_hints_match_care_role_and_location(chain_data):
    _, _, context, schedule = chain_data
    task = schedule['care'][0]
    feedback = {'conflicts': [{'code': 'NOT_PERSONNEL', 'task_id': task['task_id']}]}
    result = baseline.resource_hints(context, schedule, feedback)
    hints = result['conflicts'][0]['valid_resource_hints']
    operation = next(o for o in schedule['operations'] if o['task_id'] == task['operation_id'])
    action = next(a for p in context['patients'] for plan in p['candidate_plans'] for a in plan['actions'] if a['action_id'] == operation['action_id'])
    role = api.requirement(context['action_mapping'], action)['care']['role']
    assert hints['personnel']
    assert not hints['equipment'] and not hints['spaces']
    for rid in hints['personnel']:
        person = next(p for p in context['resources']['personnel'] if p['id'] == rid)
        assert role in person['capabilities'] and person['location'] == task['location']


def test_request_failure_retains_elapsed_audit_without_retry(tmp_path, monkeypatch):
    scheduler = scheduling_provider()
    scheduler.schedule_variant = 'L1'
    calls, _ = client_mock(monkeypatch, '', error=TimeoutError('private-test-key'))
    with pytest.raises(TimeoutError):
        asyncio.run(scheduler.propose(load_scenario()[0], feedback=None, previous_response=None, audit_dir=tmp_path))
    assert len(calls) == 1
    assert api.read(tmp_path / 'llm_request_metadata.json')['model_elapsed_s'] >= 0
    assert 'private-test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())
