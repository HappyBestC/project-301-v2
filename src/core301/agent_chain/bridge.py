"""Independent patient processes and native bulk AdvanceTime actions, without pacing."""
from concurrent.futures import ProcessPoolExecutor
import csv
import json
import math
import multiprocessing
import os
from pathlib import Path
from time import perf_counter

from pydantic import TypeAdapter

from core301.contracts.v2.injury import InjuryInput
from core301.contracts.v2.treatment import TreatmentAction
from core301.dispatch.minimal import api
from core301.pulse.injury_adapter import scalar
from core301.pulse.observation_projector import BASIC
from core301.pulse.v2.exposure_session import environment_action
from core301.pulse.v2.injury_adapter import InjuryAdapter
from core301.pulse.v2.protocol_book import OPEN_INJURIES, protocol_id
from core301.pulse.v2.treatment_adapter import TreatmentAdapter
from core301.runtime.v2.injury_registry import InjuryRegistry
from core301.runtime.v2_1.adapters import action_payload
from .audit import safe_error, write_json
from .timeline import STABILIZATION_S, global_time_min, native_time_s

TERMINAL_EVENTS = frozenset(('IrreversibleState', 'CardiacArrest'))
SAMPLE_FIELDS = ('time_min', 'pulse_time_s', 'pulse_injury_time_s', 'phase',
                 'HR_per_min', 'RR_per_min', 'SpO2', 'SBP_mmHg', 'MAP_mmHg',
                 'CardiacOutput_L_min', 'BloodVolume_mL')


def injury_payload(spec: dict) -> dict:
    injury = spec['injury']
    if injury['injury_type'] in ('carbon_monoxide_exposure', 'environmental_hypoxia'):
        gases = injury['environment_gases']
        return environment_action(gases['CarbonMonoxide'], gases['Oxygen'])
    # Dehydration is a condition, not a dynamic action: the existing adapter
    # rejects it. Do not replace the specified frozen-state/60s/onset sequence.
    return InjuryAdapter().convert_dynamic(TypeAdapter(InjuryInput).validate_python(injury))


def treatment_payload(spec: dict, event: dict) -> dict:
    injury_type = spec['injury']['injury_type']
    kind = event['action_type']
    if injury_type in OPEN_INJURIES:
        registry = InjuryRegistry(spec['patient_id'])
        registry.register({'patient_id': spec['patient_id'], 'injuries': [spec['injury']]})
        action = TypeAdapter(TreatmentAction).validate_python({
            'action_type': kind, **{k: v for k, v in event['target'].items() if k != 'patient_id'}})
        return TreatmentAdapter().convert(action, registry.sources()[0], protocol_id(injury_type, kind))
    if (injury_type == 'hemothorax' and kind in ('control_hemothorax_bleeding', 'chest_tube')) or (
        injury_type in ('carbon_monoxide_exposure', 'environmental_hypoxia') and kind == 'remove_from_exposure'
    ):
        return action_payload(kind, None)
    raise ValueError(f'No specified adapter for {injury_type}/{kind}')


class NativePulse:
    """Reuse the frozen session and read requests; bulk advancement stays in C++."""
    def __init__(self, patient_id: str):
        from core301.pulse.v2.session import ResearchPulseSession
        self.session = ResearchPulseSession(patient_id, BASIC + ('circulation.cardiac_output',))

    def initialize(self, directory: Path):
        self.session.initialize(directory / 'pulse.log')
        self.engine = self.session._native._engine
        self.fmt = self.session._native._format
        self.engine.keep_event_changes(True)

    def now(self) -> float:
        # Reading directly also works after a native terminal/failed advance.
        return float(self.engine.pull_data()[0])

    def advance(self, target_s: float) -> bool:
        dt = self.session._native._dt
        seconds = round((target_s - self.now()) / dt) * dt
        if seconds < 0:
            raise ValueError('Pulse time reversal')
        payload = {'AdvanceTime': {'Time': scalar('Time', seconds, 's')}}
        # Controller::ProcessAction(SEAdvanceTime) calls native AdvanceModelTime.
        # Do not use PulseSession.advance_time, which loops over ticks in Python.
        return self.submit(payload)

    def submit(self, payload: dict) -> bool:
        from google.protobuf.json_format import ParseDict
        from pulse.cdm.bind.Engine_pb2 import ActionListData
        batch = {'AnyAction': [payload]}
        ParseDict(batch, ActionListData())
        return bool(self.engine.process_actions(json.dumps(batch, allow_nan=False), self.fmt))

    def sample(self) -> dict:
        values = self.engine.pull_data()
        if len(values) != len(BASIC) + 1 + 4 + 1:
            raise RuntimeError('NATIVE_DATA_SHAPE')
        metrics = dict(zip(SAMPLE_FIELDS[4:], map(float, values[1:8])))
        if not all(math.isfinite(v) for v in metrics.values()):
            raise RuntimeError('NATIVE_NONFINITE_SAMPLE')
        return metrics

    def events(self) -> list:
        from google.protobuf.json_format import Parse
        from pulse.cdm.bind.Events_pb2 import EventChangeListData, eEvent
        payload = self.engine.pull_events(self.fmt)
        message = Parse(payload, EventChangeListData()) if payload else EventChangeListData()
        result = []
        for event in message.Change:
            # Protobuf JSON omits enum zero (Antidiuresis), false Active and
            # zero time values. Decode their schema defaults, not dict keys.
            clock = event.SimTime.ScalarTime
            if clock.Unit != 's':
                raise ValueError('Unexpected native event time unit')
            result.append({'event': eEvent.Name(event.Event), 'active': event.Active,
                           'pulse_time_s': float(clock.Value)})
        return result

    def close(self):
        self.session.close()


class FakePulse:
    """Synthetic clock and constant test signals, never a physiological prediction."""
    def __init__(self, patient_id: str):
        self.time = 0.0

    def initialize(self, directory: Path):
        pass

    def now(self):
        return self.time

    def advance(self, target_s):
        self.time = target_s
        return True

    def submit(self, payload):
        return True

    def sample(self):
        return dict(zip(SAMPLE_FIELDS[4:], (75.0, 12.0, 0.98, 120.0, 90.0, 5.0, 5000.0)))

    def events(self):
        return []

    def close(self):
        pass


def _adapter_reason(exc: Exception) -> dict:
    return {'code': getattr(exc, 'code', type(exc).__name__), 'detail': str(exc)}


def save_execution(directory: Path, record: dict):
    with (directory / 'samples.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(record['samples'])
    for key in ('events', 'actions'):
        write_json(directory / f'{key}.json', record[key])
    write_json(directory / 'execution.json', {k: v for k, v in record.items()
                                            if k not in ('samples', 'events', 'actions')})


def execute_patient(spec: dict, timeline: list, directory: Path, *, horizon_min: float = 120.0,
                    native: bool = True, engine=None) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    pid, arrival = spec['patient_id'], spec['arrival_time_min']
    planned = [e for e in timeline if e['patient_id'] == pid and e['event'] == 'apply_action']
    record = {
        'patient_id': pid, 'arrival_time_min': arrival, 'worker_pid': os.getpid(),
        'backend': 'native' if native else 'fake', 'samples': [], 'events': [],
        'actions': [{**e, 'planned_time_min': e['time_min'], 'actual_pulse_time_s': None,
                     'injected': False, 'accepted': None, 'status': 'PENDING'} for e in planned],
        'terminal_event': None, 'engine_failure': None, 'injury_unsupported': None,
        'treatment_incomplete': False, 'exploratory': spec['injury']['injury_type'] == 'hemothorax',
        'reached_horizon': False, 'last_pulse_time_s': None,
    }
    engine = engine or (NativePulse(pid) if native else FakePulse(pid))

    def capture(phase):
        now = engine.now()
        record['last_pulse_time_s'] = now
        record['samples'].append({'time_min': global_time_min(now, arrival), 'pulse_time_s': now,
                                  'pulse_injury_time_s': now - STABILIZATION_S, 'phase': phase,
                                  **engine.sample()})

    def collect_events():
        for event in engine.events():
            if event['pulse_time_s'] < STABILIZATION_S - 1e-6:
                continue
            event = {**event, 'time_min': global_time_min(event['pulse_time_s'], arrival)}
            record['events'].append(event)
            if event['active'] and event['event'] in TERMINAL_EVENTS:
                previous = record['terminal_event']
                if previous is None or event['pulse_time_s'] < previous['pulse_time_s']:
                    record['terminal_event'] = event

    try:
        try:
            onset = injury_payload(spec) if native else {'fake_injury': spec['injury']['injury_type']}
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            record['injury_unsupported'] = {'status': 'INJURY_UNSUPPORTED', **_adapter_reason(exc)}
            return record
        engine.initialize(directory)
        if not engine.advance(STABILIZATION_S):
            collect_events()
            if not record['terminal_event']:
                record['engine_failure'] = {'code': 'STABILIZATION_FAILED'}
            return record
        engine.events()  # The healthy prelude is outside the outcome window.
        capture('before_injury')
        if not engine.submit(onset):
            record['injury_unsupported'] = {'status': 'INJURY_UNSUPPORTED', 'code': 'NATIVE_INJURY_REJECTED',
                                            'detail': 'Native process_actions rejected the injury payload'}
            record['samples'].clear()
            return record
        record['injury_receipt'] = {'accepted': True, 'pulse_time_s': engine.now()}
        capture('after_injury')
        collect_events()
        # A fixed one-minute sampling grid plus exact action times; no interval
        # ever advances more than 60 simulated seconds.
        stops = {float(arrival + i) for i in range(1, math.ceil(horizon_min - arrival) + 1)
                 if arrival + i <= horizon_min}
        stops.update(a['time_min'] for a in planned)
        stops.add(horizon_min)
        for minute in sorted(stops):
            if record['terminal_event'] or record['engine_failure']:
                break
            target = native_time_s(minute, arrival)
            if target > engine.now() + 1e-6:
                advance_error = None
                try:
                    advanced = engine.advance(target)
                except Exception as exc:
                    advanced, advance_error = False, safe_error(exc)
                collect_events()
                capture('sample')
                if not advanced and not record['terminal_event']:
                    record['engine_failure'] = {'code': 'NATIVE_ADVANCE_FAILED', **(advance_error or {})}
                if record['terminal_event'] or record['engine_failure']:
                    break
            for action in record['actions']:
                if action['time_min'] != minute:
                    continue
                capture('before_action')
                try:
                    payload = treatment_payload(spec, action) if native else {'fake_action': action['action_type']}
                except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                    action.update(status='ACTION_UNSUPPORTED', reason=_adapter_reason(exc))
                    record['treatment_incomplete'] = True
                else:
                    action.update(injected=True, actual_pulse_time_s=engine.now())
                    action['accepted'] = engine.submit(payload)
                    action['status'] = 'ACCEPTED' if action['accepted'] else 'ACTION_UNSUPPORTED'
                    if not action['accepted']:
                        action['reason'] = {'code': 'NATIVE_ACTION_REJECTED',
                                            'detail': 'Native process_actions returned false'}
                        record['treatment_incomplete'] = True
                capture('after_action')
                collect_events()
                if record['terminal_event']:
                    break
        record['reached_horizon'] = (not record['terminal_event'] and not record['engine_failure']
                                     and engine.now() >= native_time_s(horizon_min, arrival) - 1e-6)
    except Exception as exc:
        # Never reclassify an observed terminal event as an engine failure.
        try:
            collect_events()
        except Exception:
            pass
        if not record['terminal_event']:
            record['engine_failure'] = {'code': 'WORKER_EXECUTION_FAILED', **safe_error(exc)}
    finally:
        for action in record['actions']:
            if action['status'] == 'PENDING':
                action['status'] = ('NOT_EXECUTED_INJURY_UNSUPPORTED' if record['injury_unsupported']
                                    else 'NOT_REACHED_TERMINAL' if record['terminal_event']
                                    else 'NOT_REACHED_ENGINE_FAILURE')
        engine.close()
        record['wall_elapsed_s'] = perf_counter() - start
        simulated = max(0.0, (record['last_pulse_time_s'] or STABILIZATION_S) - STABILIZATION_S)
        record['speed_ratio'] = simulated / record['wall_elapsed_s'] if record['wall_elapsed_s'] else None
        save_execution(directory, record)
    return record


def _worker(spec, timeline, directory, horizon_min, native):
    return execute_patient(spec, timeline, directory, horizon_min=horizon_min, native=native)


def execute_all(cases: list, timeline: list, run_dir: Path, *, native: bool,
                horizon_min: float = 120.0) -> dict:
    specs = {s['patient_id']: s for s in api.read(api.DATASET / 'patient_specs.json')}
    workers = min(len(cases), os.cpu_count() or 1)
    # One task per process, including machines with fewer CPUs than patients.
    # No parent/native state is inherited and no engine is shared or reused.
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                             max_tasks_per_child=1) as pool:
        pending = {c['patient_id']: pool.submit(_worker, specs[c['patient_id']], timeline,
                    str(Path(run_dir) / 'execution' / c['patient_id']), horizon_min, native) for c in cases}
        return {pid: future.result() for pid, future in pending.items()}
