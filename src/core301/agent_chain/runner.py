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
from .scheduling import FakeSchedulingProvider, LLMSchedulingProvider, REPLAY_PATH, ReplaySchedulingProvider
from .treatment import FakeTreatmentProvider, LLMTreatmentProvider, TemplateTreatmentProvider, template_decisions


def mode_providers(mode: str) -> Providers:
    if mode == 'offline':
        return Providers(FakeTreatmentProvider(template_decisions()), FakeSchedulingProvider([api.read(REPLAY_PATH)]))
    if mode == 'native_replay':
        return Providers(TemplateTreatmentProvider(), ReplaySchedulingProvider())
    if mode == 'live':
        return Providers(LLMTreatmentProvider(), LLMSchedulingProvider())
    raise ValueError('Unknown mode')


async def run_chain(mode: str, run_id: str, *, max_schedule_attempts: int = 3,
                    root: Path = RESULTS_ROOT, providers: Providers | None = None) -> dict:
    if type(max_schedule_attempts) is not int or not 1 <= max_schedule_attempts <= 5:
        raise ValueError('max_schedule_attempts must be between 1 and 5')
    if mode not in ('offline', 'native_replay', 'live'):
        raise ValueError('Unknown mode')
    providers = providers or mode_providers(mode)
    config = {'horizon_min': 120.0, 'observation_time_min': 60.0, 'max_schedule_attempts': max_schedule_attempts}
    directory = create_run(run_id, mode, {'treatment': type(providers.treatment).__name__,
                           'scheduling': type(providers.scheduling).__name__,
                           'pulse': 'FakePulse' if mode == 'offline' else 'NativePulse'}, config, root)
    initial = {'run_id': run_id, 'run_dir': str(directory), 'mode': mode, 'horizon_min': 120.0,
               'status': 'running', 'schedule_attempts': [], 'feedback': None,
               'previous_response': None, 'accepted_schedule': None}
    started = perf_counter()
    try:
        state = await build_graph(providers, config).ainvoke(initial, {'recursion_limit': 30})
    except Exception as exc:
        error = safe_error(exc)
        write_json(directory / 'runner_error.json', error)
        finish_run(directory, {'run_id': run_id, 'mode': mode, 'status': 'running',
                               'aborted': True, 'error': error, 'wall_elapsed_s': perf_counter() - started})
        raise
    summary = {
        'run_id': run_id, 'mode': mode, 'status': state['status'], 'horizon_min': 120.0,
        'loaded_patients': len(state['cases']), 'excluded_patients': state.get('excluded_patients', {}),
        'schedule_attempts': len(state['schedule_attempts']),
        'accepted_patients': len(state['accepted_schedule']['selections']) if state['accepted_schedule'] else 0,
        'last_conflicts': len(state.get('validation', {}).get('conflicts', [])),
        'execution_patients': len(state.get('execution', {})),
        'model_calls_enabled': mode == 'live', 'synthetic_physiology': mode == 'offline',
        'outcomes': state.get('outcomes', {}).get('summary'), 'wall_elapsed_s': perf_counter() - started,
    }
    finish_run(directory, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('offline', 'native_replay', 'live'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--max-schedule-attempts', type=int, default=3)
    args = parser.parse_args()
    summary = asyncio.run(run_chain(args.mode, args.run_id, max_schedule_attempts=args.max_schedule_attempts))
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if summary['status'] in ('completed', 'execution_partial') else 1


if __name__ == '__main__':
    raise SystemExit(main())
