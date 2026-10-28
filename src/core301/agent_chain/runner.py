"""Run offline or native replay; live is available only by explicit CLI selection."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from core301.dispatch.minimal import api
from .audit import RESULTS_ROOT, create_run, finish_run, safe_error, write_json
from .graph import build_graph
from .nodes import Providers
from .scheduling import FakeSchedulingProvider, LLMSchedulingProvider, ReplaySchedulingProvider
from .scenarios import SCENARIOS, scenario_paths
from .treatment import (DEFAULT_MAX_TOKENS, FakeTreatmentProvider, LLMTreatmentProvider,
                        TemplateTreatmentProvider, template_decisions, validate_max_tokens)


def _mode_paths(mode: str, scenario: str) -> dict:
    if mode not in ('offline', 'native_replay', 'live'):
        raise ValueError('Unknown mode')
    paths = scenario_paths(scenario)
    if mode in ('offline', 'native_replay') and paths['replay_schedule'] is None:
        raise ValueError(f'{scenario} has no replay schedule; {mode} mode is unavailable')
    return paths


def mode_providers(mode: str, scenario: str = 'run_001', *, treatment_max_tokens: int = DEFAULT_MAX_TOKENS) -> Providers:
    paths = _mode_paths(mode, scenario)
    if mode == 'offline':
        return Providers(FakeTreatmentProvider(template_decisions(paths['dataset_dir'])),
                         FakeSchedulingProvider([api.read(paths['replay_schedule'])]))
    if mode == 'native_replay':
        return Providers(TemplateTreatmentProvider(paths['dataset_dir']),
                         ReplaySchedulingProvider(paths['replay_schedule']))
    if mode == 'live':
        return Providers(LLMTreatmentProvider(treatment_max_tokens), LLMSchedulingProvider())
    raise ValueError('Unknown mode')


async def run_chain(mode: str, run_id: str, *, max_schedule_attempts: int = 3,
                    root: Path = RESULTS_ROOT, providers: Providers | None = None,
                    scenario: str = 'run_001', treatment_max_tokens: int = DEFAULT_MAX_TOKENS) -> dict:
    if type(max_schedule_attempts) is not int or not 1 <= max_schedule_attempts <= 5:
        raise ValueError('max_schedule_attempts must be between 1 and 5')
    validate_max_tokens(treatment_max_tokens)
    _mode_paths(mode, scenario)  # Reject unavailable replay before providers or any run files.
    providers = providers or mode_providers(mode, scenario, treatment_max_tokens=treatment_max_tokens)
    config = {'horizon_min': 120.0, 'observation_time_min': 60.0, 'max_schedule_attempts': max_schedule_attempts,
              'treatment_max_tokens': (providers.treatment.max_tokens if isinstance(providers.treatment, LLMTreatmentProvider)
                                       else treatment_max_tokens)}
    directory = create_run(run_id, mode, {'treatment': type(providers.treatment).__name__,
                           'scheduling': type(providers.scheduling).__name__,
                           'pulse': 'FakePulse' if mode == 'offline' else 'NativePulse'}, config, root,
                           scenario=scenario)
    initial = {'run_id': run_id, 'run_dir': str(directory), 'mode': mode, 'horizon_min': 120.0,
               'scenario': scenario, 'status': 'running', 'schedule_attempts': [], 'feedback': None,
               'previous_response': None, 'accepted_schedule': None,
               'treatment_stage': 'not_reached', 'schedule_stage': 'not_reached'}
    state = initial.copy()
    progress = {'active_stage': None, 'treatment_stage': 'not_reached', 'schedule_stage': 'not_reached'}
    started = perf_counter()
    try:
        async for update in build_graph(providers, config, progress).astream(
                initial, {'recursion_limit': 30}, stream_mode='updates'):
            for changes in update.values():
                state.update(changes)
    except Exception as exc:
        error = safe_error(exc)
        write_json(directory / 'runner_error.json', error)
        state.update(status='aborted', error=error)
        for stage in ('treatment', 'schedule'):
            state[stage + '_stage'] = ('aborted' if progress['active_stage'] == stage
                                       else progress[stage + '_stage'])
    summary = {
        'run_id': run_id, 'mode': mode, 'status': state['status'], 'horizon_min': 120.0,
        'treatment_stage': state['treatment_stage'], 'schedule_stage': state['schedule_stage'],
        'loaded_patients': len(state.get('cases', [])), 'excluded_patients': state.get('excluded_patients', {}),
        'schedule_attempts': len(state['schedule_attempts']),
        'accepted_patients': len(state['accepted_schedule']['selections']) if state['accepted_schedule'] else 0,
        'last_conflicts': len(state.get('validation', {}).get('conflicts', [])),
        'execution_patients': len(state.get('execution', {})),
        'model_calls_enabled': mode == 'live', 'synthetic_physiology': mode == 'offline',
        'outcomes': state.get('outcomes', {}).get('summary'), 'wall_elapsed_s': perf_counter() - started,
    }
    for key in ('schedule_error', 'error'):
        if key in state:
            summary[key] = state[key]
    finish_run(directory, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('offline', 'native_replay', 'live'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--scenario', choices=tuple(SCENARIOS), default='run_001')
    parser.add_argument('--max-schedule-attempts', type=int, default=3)
    parser.add_argument('--treatment-max-tokens', type=int, default=DEFAULT_MAX_TOKENS)
    args = parser.parse_args()
    summary = asyncio.run(run_chain(args.mode, args.run_id, max_schedule_attempts=args.max_schedule_attempts,
                                    scenario=args.scenario, treatment_max_tokens=args.treatment_max_tokens))
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if summary['status'] in ('completed', 'execution_partial') else 1


if __name__ == '__main__':
    raise SystemExit(main())
