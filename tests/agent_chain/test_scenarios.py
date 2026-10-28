import asyncio
import hashlib
import json
import sys

import pytest

from core301.agent_chain import bridge, runner
from core301.agent_chain.audit import create_run
from core301.agent_chain.nodes import Nodes, Providers
from core301.agent_chain.scenarios import SCENARIOS, scenario_paths
from core301.agent_chain.scheduling import FakeSchedulingProvider, ReplaySchedulingProvider
from core301.agent_chain.treatment import TemplateTreatmentProvider
from core301.dispatch.minimal import api
from core301.paths import PROJECT_ROOT


@pytest.mark.parametrize('mode', ['offline', 'native_replay'])
def test_run_002_rejected_before_provider_or_run_directory(mode, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No providers may be constructed for unavailable replay')
    monkeypatch.setattr(runner, 'mode_providers', forbidden)
    for providers in (None, object()):
        with pytest.raises(ValueError, match=f'run_002 has no replay schedule; {mode}'):
            asyncio.run(runner.run_chain(mode, 'unavailable', scenario='run_002',
                                        root=tmp_path, providers=providers))
    assert list(tmp_path.iterdir()) == []


def test_unknown_scenario_and_missing_replay_fail_explicitly(tmp_path):
    with pytest.raises(ValueError, match='Unknown scenario'):
        asyncio.run(runner.run_chain('offline', 'unknown', scenario='unknown', root=tmp_path))
    with pytest.raises(ValueError, match='no replay schedule'):
        ReplaySchedulingProvider(None)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('argument,expected', [(None, 'run_001'), ('run_001', 'run_001'), ('run_002', 'run_002')])
def test_cli_threads_scenario_argument(argument, expected, monkeypatch, capsys):
    calls = []

    async def capture(mode, run_id, **kwargs):
        calls.append((mode, run_id, kwargs))
        return {'status': 'completed'}
    monkeypatch.setattr(runner, 'run_chain', capture)
    argv = ['runner', '--mode', 'offline', '--run-id', 'cli-test']
    if argument:
        argv += ['--scenario', argument]
    monkeypatch.setattr(sys, 'argv', argv)
    assert runner.main() == 0
    assert calls == [('offline', 'cli-test', {'max_schedule_attempts': 3, 'scenario': expected})]
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'


@pytest.mark.parametrize('scenario', ['run_001', 'run_002'])
def test_manifest_identifies_and_hashes_every_scenario_file(scenario, tmp_path):
    directory = create_run('manifest', 'offline', {}, {}, tmp_path, scenario=scenario)
    manifest = api.read(directory / 'manifest.json')
    assert manifest['scenario'] == scenario
    expected = {}
    for key in ('config_dir', 'dataset_dir'):
        assert manifest[key] == SCENARIOS[scenario][key]
        for path in (PROJECT_ROOT / manifest[key]).rglob('*'):
            if path.is_file():
                expected[str(path.relative_to(PROJECT_ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest['scenario_files_sha256'] == expected


def test_run_002_input_nodes_never_read_run_001_dataset(tmp_path, monkeypatch):
    paths = scenario_paths('run_002')
    expected = api.build_input(*api.load_config(paths['config_dir']), api.load_cases(paths['dataset_dir']))
    original = api.read

    def read_target_only(path):
        assert not str(path).startswith(str(api.DATASET) + '/')
        return original(path)
    monkeypatch.setattr(api, 'read', read_target_only)
    provider = TemplateTreatmentProvider(paths['dataset_dir'])
    seen = []

    def capture_execute(cases, timeline, run_dir, **kwargs):
        seen.append(kwargs['dataset_dir'])
        return {}
    nodes = Nodes(Providers(provider, FakeSchedulingProvider([]), capture_execute), {'max_schedule_attempts': 3})
    state = {'scenario': 'run_002', 'mode': 'offline', 'run_dir': str(tmp_path), 'horizon_min': 120.0}
    state.update(nodes.load_scenario(state))
    state.update(asyncio.run(nodes.treatment(state)))
    state.update(nodes.build_dispatch_input(state))
    assert state['dispatch_input'] == expected
    assert state['excluded_patients'] == {}
    assert {p['location'] for p in state['cases']} == {'F1', 'F2'}
    # Only inspect argument propagation here: no schedule, graph or execution run.
    state['timeline'] = []
    nodes.execute(state)
    assert seen == [paths['dataset_dir']]


def test_execute_all_passes_selected_dataset_specs_to_workers(tmp_path, monkeypatch):
    paths = scenario_paths('run_002')
    specs = api.read(paths['dataset_dir'] / 'patient_specs.json')
    received = []

    class Pool:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, worker, spec, *args):
            received.append(spec)
            class Future:
                def result(self):
                    return {'patient_id': spec['patient_id']}
            return Future()
    monkeypatch.setattr(bridge, 'ProcessPoolExecutor', Pool)
    cases = api.load_cases(paths['dataset_dir'])
    result = bridge.execute_all(cases, [], tmp_path, native=False, dataset_dir=paths['dataset_dir'])
    assert received == specs
    assert len(result) == 16


def test_default_run_001_providers_retain_baseline_sources():
    providers = runner.mode_providers('native_replay')
    assert providers.scheduling.path == scenario_paths('run_001')['replay_schedule']
    assert providers.treatment.responses == TemplateTreatmentProvider(api.DATASET).responses
