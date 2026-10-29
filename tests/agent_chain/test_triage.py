import asyncio
import copy
import hashlib
import json
import sys

import pytest

from core301.agent_chain import baseline, nodes, runner, treatment
from core301.agent_chain.nodes import Nodes, Providers
from core301.agent_chain.scenarios import scenario_paths
from core301.agent_chain.scheduling import FakeSchedulingProvider, REPLAY_PATH
from core301.dispatch.minimal import api
from core301.triage.service import triage_cases, with_triage_tags
from tests.agent_chain.test_graph import fast_execute
from tests.agent_chain.test_llm_baseline import empty_schedule, fake_native
from tests.agent_chain.test_provider_audit import client_mock, scheduling_provider


OLD_URGENCY = ('每名伤员的 `urgency` 给出了 Pulse 测得的时效信息：`effective_after_injury_min` 的键是'
               '"方案第一个动作的操作结束时刻减去受伤时刻"（分钟），值是该时刻生效时的死亡与否和 CO 缺损；'
               '`untreated` 是不处置的结局。')
NEW_TRIAGE = ('每名伤员的 `triage_tag` 是分诊器给出的分级：`red` 为立即处置（有生命危险，及时处置可以救活），'
              '`yellow` 为延迟处置（需要处置，暂无生命危险），`green` 为轻伤（可以最后处置），'
              '`black` 为已无呼吸（不分配救治资源）。资源不足时，按分级从高到低优先安排。')


@pytest.mark.parametrize('mode,scenario', [('offline', 'run_001'), ('native_replay', 'run_001'),
                                         ('live', 'run_002'), ('live_schedule', 'run_002')])
def test_all_modes_triage_before_treatment_without_changing_its_input(tmp_path, mode, scenario):
    directory = tmp_path / 'run'
    dataset = scenario_paths(scenario)['dataset_dir']
    original_cases = api.load_cases(dataset)
    mapping = api.load_config(scenario_paths(scenario)['config_dir'])[1]
    expected_inputs = {c['patient_id']: treatment.build_treatment_input(c, mapping) for c in original_cases}
    treatment_calls = []

    class CheckedTreatment(treatment.TemplateTreatmentProvider):
        async def propose(self, payload, *, audit_dir):
            triage = api.read(directory / 'triage.json')
            state = api.read(directory / 'state/load_scenario.json')
            assert state['triage'] == triage
            assert triage['summary'] == dict(red=7, yellow=0, green=9, black=0)
            assert payload == expected_inputs[payload['patient_id']]
            treatment_calls.append(payload['patient_id'])
            return await super().propose(payload, audit_dir=audit_dir)

    scheduler = FakeSchedulingProvider([api.read(REPLAY_PATH) if scenario == 'run_001' else empty_schedule()])
    providers = Providers(CheckedTreatment(dataset), scheduler, fast_execute if mode == 'offline' else fake_native)
    result = asyncio.run(runner.run_chain(mode, 'run', root=tmp_path, scenario=scenario, providers=providers))
    assert result['status'] == 'completed'
    assert len(treatment_calls) == 16
    expected_context = api.build_input(*api.load_config(scenario_paths(scenario)['config_dir']),
                                       original_cases, horizon_min=120.0, observation_time_min=60.0)
    assert api.read(directory / 'dispatch_input.json') == expected_context
    assert scheduler.calls[0]['dispatch_input'] == expected_context
    assert 'triage.json' in api.read(directory / 'sha256_manifest.json')


@pytest.mark.parametrize('field', ['heart_rate', 'respiration_rate'])
def test_missing_vitals_abort_before_any_treatment_or_scheduling(tmp_path, monkeypatch, field):
    providers = runner.mode_providers('offline')
    cases = api.load_cases()
    cases[0]['observation']['vitals'][field]['status'] = 'unavailable'
    monkeypatch.setattr(api, 'load_cases', lambda path: cases)

    async def forbidden(*args, **kwargs):
        pytest.fail('Unavailable vitals must abort before the providers')

    monkeypatch.setattr(providers.treatment, 'propose', forbidden)
    monkeypatch.setattr(providers.scheduling, 'propose', forbidden)
    result = asyncio.run(runner.run_chain('offline', 'run', root=tmp_path, providers=providers))
    assert result['status'] == 'aborted'
    assert result['error']['error_type'] == 'ValueError'
    assert result['treatment_stage'] == result['schedule_stage'] == 'not_reached'
    assert not (tmp_path / 'run/triage.json').exists()
    assert not (tmp_path / 'run/treatment').exists()


def test_l2_model_copy_only_exposes_tags_and_is_independent():
    dataset = scenario_paths('run_002')['dataset_dir']
    cases = api.load_cases(dataset)
    context = api.build_input(*api.load_config(scenario_paths('run_002')['config_dir']), cases)
    triage = triage_cases(cases, api.read(dataset / 'patient_specs.json'))
    original = copy.deepcopy((context, triage))
    model_input = with_triage_tags(context, triage)
    for old, new, result in zip(context['patients'], model_input['patients'], triage['patients']):
        assert new == {**{k: v for k, v in old.items() if k != 'observation'}, 'triage_tag': result['tag']}
        assert not {'observation', 'urgency', 'reason', 'inputs', 'wounds'} & set(new)
    assert {k: v for k, v in model_input.items() if k != 'patients'} == {
        k: v for k, v in context.items() if k != 'patients'}
    model_input['patients'][0]['candidate_plans'][0]['actions'].clear()
    assert (context, triage) == original


def test_l2_schedule_retries_keep_original_validator_context(tmp_path, monkeypatch):
    scheduler = FakeSchedulingProvider([empty_schedule('no_feasible_schedule_found')])
    providers = Providers(treatment.TemplateTreatmentProvider(scenario_paths('run_002')['dataset_dir']), scheduler, fake_native)
    engine = Nodes(providers, {'schedule_variant': 'L2', 'max_schedule_attempts': 3})
    state = dict(run_dir=str(tmp_path), scenario='run_002', mode='live_schedule',
                 schedule_attempts=[], feedback=None, previous_response=None, accepted_schedule=None)
    state.update(engine.load_scenario(state))
    state.update(asyncio.run(engine.treatment(state)))
    state.update(engine.build_dispatch_input(state))
    original = copy.deepcopy(state['dispatch_input'])
    validations = []
    validate = nodes.independently_validate

    def checked_validate(context, *args):
        assert context is state['dispatch_input']
        assert context == original
        validations.append(copy.deepcopy(context))
        return validate(context, *args)

    monkeypatch.setattr(nodes, 'independently_validate', checked_validate)
    for attempt in range(1, 4):
        state.update(asyncio.run(engine.schedule(state)))
        state.update(engine.validate(state))
        payload = api.read(tmp_path / f'schedule/attempt_{attempt:02}/request.json')['dispatch_input']
        assert payload == scheduler.calls[-1]['dispatch_input']
        assert payload == with_triage_tags(original, state['triage'])
    assert len(validations) == 3 and state['dispatch_input'] == original
    assert state['schedule_stage'] == 'partial'


def test_l2_projection_matches_patient_ids_after_exclusion():
    original = {'patients': [dict(patient_id='P02', observation={'x': 1}),
                             dict(patient_id='P01', observation={'x': 2})]}
    triage = {'patients': [dict(patient_id='P01', tag='red'), dict(patient_id='P02', tag='green'),
                           dict(patient_id='excluded', tag='black')]}
    assert with_triage_tags(original, triage) == {'patients': [dict(patient_id='P02', triage_tag='green'),
                                                             dict(patient_id='P01', triage_tag='red')]}


def test_l2_prompt_changes_only_the_user_confirmed_urgency_sentence():
    before = baseline.prompt_path('L1').read_bytes()
    after = baseline.prompt_path('L2').read_bytes()
    assert before.count(OLD_URGENCY.encode()) == 1
    assert after == before.replace(OLD_URGENCY.encode(), NEW_TRIAGE.encode(), 1)
    assert '排入人数本身不是目标：资源不足时，优先保证会因延误而死亡的伤员。'.encode() in after
    spec = (baseline.PROJECT_ROOT / 'docs/TRIAGE_V1_DEV_SPEC.md').read_text()
    assert NEW_TRIAGE == next(line.strip()[2:] for line in spec.splitlines()
                              if line.strip().startswith('> 每名伤员的 `triage_tag`'))


def test_live_schedule_l2_end_to_end_with_mock_sdk(tmp_path, monkeypatch):
    dataset = scenario_paths('run_002')['dataset_dir']
    original_cases = api.load_cases(dataset)
    resources, mapping = api.load_config(scenario_paths('run_002')['config_dir'])
    original_context = api.build_input(resources, mapping, original_cases, horizon_min=120.0, observation_time_min=60.0)

    class ForbiddenTreatment(treatment.LLMTreatmentProvider):
        def __init__(self, *args, **kwargs):
            pytest.fail('L2 must not construct a treatment model')

    monkeypatch.setattr(runner, 'LLMTreatmentProvider', ForbiddenTreatment)
    scheduler = scheduling_provider()
    scheduler.schedule_variant = 'L2'

    def configured_scheduler(**kwargs):
        assert kwargs == {'schedule_variant': 'L2'}
        return scheduler

    monkeypatch.setattr(runner, 'LLMSchedulingProvider', configured_scheduler)
    calls, settings = client_mock(monkeypatch, json.dumps(empty_schedule('no_feasible_schedule_found')))
    providers = runner.mode_providers('live_schedule', 'run_002', schedule_variant='L2')
    assert isinstance(providers.treatment, treatment.TemplateTreatmentProvider)
    providers.execute = fake_native
    result = asyncio.run(runner.run_chain('live_schedule', 'run', root=tmp_path,
        scenario='run_002', schedule_variant='L2', providers=providers))
    assert result['status'] == 'completed' and result['execution_patients'] == 16
    assert result['schedule_stage'] == 'partial' and len(calls) == 3
    assert all(s['max_retries'] == 0 for s in settings)
    triage = api.read(tmp_path / 'run/triage.json')
    for attempt, call in enumerate(calls, 1):
        messages = call['messages']
        assert messages[0]['content'].encode() == baseline.prompt_path('L2').read_bytes()
        payload = json.loads(messages[1]['content'])
        assert payload == with_triage_tags(original_context, triage)
        directory = tmp_path / f'run/schedule/attempt_{attempt:02}'
        assert api.read(directory / 'request.json')['dispatch_input'] == payload
        assert api.read(directory / 'request_messages.json') == messages
        assert api.read(directory / 'validation.json')['conflicts'] == []
    assert api.read(tmp_path / 'run/dispatch_input.json') == original_context
    parameters = api.read(tmp_path / 'run/manifest.json')['parameters']
    assert parameters['schedule_variant'] == 'L2'
    assert parameters['prompt_sha256'] == hashlib.sha256(baseline.prompt_path('L2').read_bytes()).hexdigest()
    assert parameters['tables_sha256'] == {} and parameters['tables'] is None
    for case in original_cases:
        assert api.read(tmp_path / f"run/treatment/{case['patient_id']}/request.json") == treatment.build_treatment_input(case, mapping)


def test_runner_cli_accepts_l2_without_tables(monkeypatch, capsys):
    calls = []

    async def fake_run(mode, run_id, **kwargs):
        calls.append((mode, run_id, kwargs))
        return {'status': 'completed'}

    monkeypatch.setattr(runner, 'run_chain', fake_run)
    monkeypatch.setattr(sys, 'argv', ['runner', '--mode', 'live_schedule', '--run-id', 'test-L2',
                                    '--scenario', 'run_002', '--schedule-variant', 'L2'])
    assert runner.main() == 0
    assert len(calls) == 1 and calls[0][:2] == ('live_schedule', 'test-L2')
    assert calls[0][2]['schedule_variant'] == 'L2' and calls[0][2]['tables'] is None
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'
