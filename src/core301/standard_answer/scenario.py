"""Run_002 inputs, with severity-only overrides kept outside the dataset."""
import copy
from pathlib import Path

from core301.agent_chain.scenarios import scenario_paths
from core301.dispatch.minimal import api

CO_LEVELS = (0.001, 0.0025, 0.005, 0.0075, 0.01)
O2_LEVELS = (0.16, 0.14, 0.12, 0.10, 0.08)


def load_scenario(scenario='run_002'):
    definition = {'base': 'run_002', 'overrides': {}} if scenario == 'run_002' else (
        copy.deepcopy(scenario) if isinstance(scenario, dict) else api.read(Path(scenario)))
    if set(definition) != {'base', 'overrides'} or definition['base'] != 'run_002':
        raise ValueError('V1 requires run_002 or {base: run_002, overrides: {...}}')
    paths = scenario_paths('run_002')
    resources, mapping = api.load_config(paths['config_dir'])
    cases = api.load_cases(paths['dataset_dir'])
    base_specs = api.read(paths['dataset_dir'] / 'patient_specs.json')
    specs = {s['patient_id']: copy.deepcopy(s) for s in base_specs}
    if not isinstance(definition['overrides'], dict):
        raise ValueError('overrides must be an object')
    for pid, patch in definition['overrides'].items():
        if pid not in specs or not isinstance(patch, dict):
            raise ValueError(f'Invalid patient override: {pid}')
        injury = specs[pid]['injury']
        kind = injury['injury_type']
        if 'environment_gases' in injury:
            gas = 'CarbonMonoxide' if kind == 'carbon_monoxide_exposure' else 'Oxygen'
            if set(patch) != {'environment_gases'} or not isinstance(patch['environment_gases'], dict) or set(patch['environment_gases']) != {gas}:
                raise ValueError(f'{pid}: only environment_gases.{gas} may be overridden')
            level = patch['environment_gases'][gas]
            levels = CO_LEVELS if gas == 'CarbonMonoxide' else O2_LEVELS
            if type(level) not in (int, float) or level not in levels:
                raise ValueError(f'{pid}: 没有对应反应表: {gas}={level}')
            gases = injury['environment_gases']
            gases[gas] = level
            if gas == 'Oxygen':
                gases['CarbonMonoxide'] = 0.0
            gases['CarbonDioxide'] = 0.0004
            gases['Nitrogen'] = 1 - gases['Oxygen'] - 0.0004 - gases['CarbonMonoxide']
        else:
            if set(patch) != {'severity'} or type(patch['severity']) not in (int, float) or not 0 <= patch['severity'] <= 1:
                raise ValueError(f'{pid}: only finite severity in [0, 1] may be overridden')
            injury['severity'] = patch['severity']
    context = api.build_input(resources, mapping, cases, horizon_min=120.0)
    return context, specs, {s['patient_id']: s for s in base_specs}, definition
