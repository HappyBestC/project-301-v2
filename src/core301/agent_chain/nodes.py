"""Graph node work; the graph module contains only wiring and routing."""
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core301.dispatch.minimal import api, feedback, validation
from core301.dispatch.minimal.models import Schedule
from . import outcomes, timeline
from .audit import safe_error, snapshot, write_json
from .bridge import execute_all
from .scheduling import SchedulingProvider
from .treatment import TreatmentProvider, admit, build_treatment_input


@dataclass
class Providers:
    treatment: TreatmentProvider
    scheduling: SchedulingProvider
    execute: Callable = execute_all


def independently_validate(context: dict, candidate) -> dict:
    result = validation.validate_schedule(context, candidate)
    if not result['conflicts'] and not Schedule.model_validate(candidate).demonstration_only:
        result.update(known_constraints_passed=False, fully_verified=False, status='conflicts',
                      effects_status='rejected', projected_occupancy=[], projected_inventory_changes=[])
        result['conflicts'].append({'code': 'DEMONSTRATION_FLAG_REQUIRED',
                                    'detail': 'This connection cannot authorize execution'})
    return result


def acceptable(result: dict) -> bool:
    return not result['conflicts'] and all(r['reason_code'] == 'missing_parameters'
                                           for r in result['unscheduled_reasons'])


class Nodes:
    def __init__(self, providers: Providers, config: dict):
        self.providers, self.config = providers, config

    def load_scenario(self, state):
        resources, mapping = api.load_config()
        cases = api.load_cases()
        if len(cases) != 16 or {c['patient_id'] for c in cases} != {f'P{i:02}' for i in range(1, 17)}:
            raise ValueError('Expected P01–P16 exactly once')
        for case in cases:
            case.pop('candidate_plans')
        return snapshot(state, 'load_scenario', {'cases': cases, 'resources': resources, 'mapping': mapping})

    async def treatment(self, state):
        decisions, excluded = {}, {}
        for case in state['cases']:
            pid = case['patient_id']
            directory = Path(state['run_dir']) / 'treatment' / pid
            directory.mkdir(parents=True, exist_ok=False)
            payload = build_treatment_input(case, state['mapping'])
            write_json(directory / 'request.json', payload)
            raw = None
            try:
                raw = await self.providers.treatment.propose(copy.deepcopy(payload), audit_dir=directory)
                (directory / 'response.txt').write_text(raw)
            except Exception as exc:
                failure = safe_error(exc)
                result = {'admitted': False, 'stage': 'provider', 'error': failure}
                excluded[pid] = 'TREATMENT_CALL_FAILED:' + failure['error_type']
            else:
                try:
                    decision, plans = admit(raw, payload, state['mapping'],
                                            plan_status=self.providers.treatment.plan_status)
                    result = {'admitted': True, 'decision': decision, 'candidate_plans': plans}
                except (ValueError, KeyError, TypeError) as exc:
                    # Admission errors describe JSON/contract issues, never SDK headers.
                    result = {'admitted': False, 'stage': 'admission', 'error': {'detail': str(exc)}}
                    excluded[pid] = 'TREATMENT_ADMISSION_FAILED:' + str(exc)
            write_json(directory / 'admission.json', result)
            decisions[pid] = {'raw_response': raw, **result}
        return snapshot(state, 'treatment', {'treatment_decisions': decisions, 'excluded_patients': excluded,
                                             'status': 'treatment_failed' if len(excluded) == len(state['cases']) else 'running'})

    def build_dispatch_input(self, state):
        cases = [{**copy.deepcopy(case), 'candidate_plans': copy.deepcopy(
            state['treatment_decisions'][case['patient_id']]['candidate_plans'])}
            for case in state['cases'] if case['patient_id'] not in state['excluded_patients']]
        context = api.build_input(state['resources'], state['mapping'], cases,
                                  horizon_min=120.0, observation_time_min=60.0)
        write_json(Path(state['run_dir']) / 'dispatch_input.json', context)
        return snapshot(state, 'build_dispatch_input', {'dispatch_input': context})

    async def schedule(self, state):
        attempts = copy.deepcopy(state['schedule_attempts'])
        n = len(attempts) + 1
        directory = Path(state['run_dir']) / 'schedule' / f'attempt_{n:02}'
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / 'request.json', {'dispatch_input': state['dispatch_input'],
                   'feedback': state['feedback'], 'previous_response': state['previous_response']})
        try:
            proposal = await self.providers.scheduling.propose(copy.deepcopy(state['dispatch_input']),
                feedback=copy.deepcopy(state['feedback']), previous_response=state['previous_response'], audit_dir=directory)
        except Exception as exc:
            proposal = {'schedule': None, 'raw_response': None, 'metadata': {'request_error': safe_error(exc)}}
            write_json(directory / 'request_error.json', proposal['metadata']['request_error'])
        attempt = {'attempt': n, 'candidate': proposal['schedule'], 'raw_response': proposal['raw_response'],
                   'metadata': proposal['metadata'], 'provider_validation': proposal.get('validation')}
        write_json(directory / 'candidate_schedule.json', attempt['candidate'])
        write_json(directory / 'response_metadata.json', attempt['metadata'])
        if attempt['raw_response'] is not None:
            (directory / 'response.txt').write_text(attempt['raw_response'])
        attempts.append(attempt)
        return snapshot(state, 'schedule', {'schedule_attempts': attempts,
                                            'previous_response': attempt['raw_response']})

    def validate(self, state):
        attempts = copy.deepcopy(state['schedule_attempts'])
        current = attempts[-1]
        context = state['dispatch_input']
        result = independently_validate(context, current['candidate'])
        directory = Path(state['run_dir']) / 'schedule' / f"attempt_{current['attempt']:02}"
        current.update(validation=result, conflicts=len(result['conflicts']),
                       selected_patients=result.get('scheduled_patients', 0))
        stop_error = None
        if current['provider_validation'] is not None and current['provider_validation'] != result:
            stop_error = {'code': 'PROVIDER_VALIDATION_MISMATCH',
                          'detail': 'Independent validation differs from the provider result'}
        if 'request_error' in current['metadata']:
            stop_error = {'code': 'SCHEDULE_REQUEST_FAILED', **current['metadata']['request_error']}
        # Reconstruct the exact existing feedback bookkeeping from JSON history.
        history, previous_selected, latest_feedback = {}, set(), None
        for attempt in attempts:
            candidate = attempt['candidate'] if isinstance(attempt['candidate'], dict) else {}
            # A schema-invalid selections value cannot be interpreted as a set
            # of patients. Keep its raw candidate above and feed the existing
            # feedback builder an uninterpretable empty object instead.
            if not isinstance(candidate.get('selections'), dict):
                candidate = {}
            latest_feedback = feedback.build_feedback(context, candidate, attempt['validation'],
                                attempt['attempt'], history, previous_selected)
            previous_selected = set(candidate.get('selections', {}))
        current['feedback'] = latest_feedback
        write_json(directory / 'validation.json', result)
        write_json(directory / 'feedback.json', latest_feedback)
        # Keep the largest conflict-free candidate, including coverage retries,
        # but only the explicitly allowed all/missing_parameters results execute.
        passed = [a for a in attempts if not a['validation']['conflicts']]
        best = max(passed, key=lambda a: a['validation']['scheduled_patients']) if passed else None
        eligible = [a for a in passed if acceptable(a['validation'])]
        accepted = max(eligible, key=lambda a: a['validation']['scheduled_patients']) if eligible else None
        current['best_passed_attempt'] = best['attempt'] if best else None
        status = 'running'
        if stop_error:
            current['error'] = stop_error
            write_json(directory / 'error.json', stop_error)
            status, accepted = 'schedule_failed', None
        elif accepted is None and len(attempts) >= self.config['max_schedule_attempts']:
            status = 'schedule_failed'
        if accepted:
            write_json(Path(state['run_dir']) / 'schedule.json', accepted['candidate'])
        return snapshot(state, 'validate', {
            'schedule_attempts': attempts, 'feedback': latest_feedback, 'validation': result,
            'accepted_schedule': accepted['candidate'] if accepted else None, 'status': status,
        })

    def build_timeline(self, state):
        events = timeline.build_timeline(state['cases'], state['dispatch_input'], state['accepted_schedule'])
        write_json(Path(state['run_dir']) / 'timeline.json', events)
        return snapshot(state, 'build_timeline', {'timeline': events})

    def execute(self, state):
        execution = self.providers.execute(state['cases'], state['timeline'], Path(state['run_dir']),
                                           native=state['mode'] != 'offline', horizon_min=state['horizon_min'])
        return snapshot(state, 'execute', {'execution': execution})

    def evaluate(self, state):
        result = outcomes.evaluate(state['execution'], state['horizon_min'])
        partial = any(p['engine_failure'] or p['injury_unsupported'] or p['treatment_incomplete']
                      for p in result['patients'].values())
        write_json(Path(state['run_dir']) / 'outcomes.json', result)
        return snapshot(state, 'evaluate', {'outcomes': result, 'status': 'execution_partial' if partial else 'completed'})
