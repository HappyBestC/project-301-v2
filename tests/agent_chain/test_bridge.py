import copy
import json
import os
from types import SimpleNamespace

import pytest

from core301.agent_chain import bridge, outcomes, timeline
from core301.dispatch.minimal import api


def spec(pid='P01'):
    return next(p for p in api.read(api.DATASET / 'patient_specs.json') if p['patient_id'] == pid)


def action(pid='P01', minute=3.0, kind='control_external_bleeding'):
    return {'event': 'apply_action', 'patient_id': pid, 'task_id': pid + '-task',
            'action_id': pid + '-action', 'action_type': kind,
            'target': {'patient_id': pid, 'compartment': 'RightLeg'},
            'location': 'A', 'time_min': minute}


class ObservedFake(bridge.FakePulse):
    def __init__(self, pid):
        super().__init__(pid)
        self.advances, self.submitted = [], []
        self.initialized = False

    def initialize(self, directory):
        self.initialized = True

    def advance(self, target_s):
        self.advances.append((self.time, target_s))
        return super().advance(target_s)

    def submit(self, payload):
        self.submitted.append((self.now(), copy.deepcopy(payload)))
        return True


@pytest.mark.parametrize('pid,arrival', [('P01', 0.0), ('P09', 10.0), ('P15', 20.0)])
def test_action_injection_clock_and_sampling(pid, arrival, tmp_path):
    engine = ObservedFake(pid)
    planned = action(pid, arrival + 2.5)
    record = bridge.execute_patient(spec(pid), [planned], tmp_path, native=False, engine=engine)
    assert engine.advances[0] == (0.0, 60.0)
    assert max(end - start for start, end in engine.advances) <= 60
    assert engine.submitted[0][0] == 60.0  # injury onset after the healthy prelude
    assert engine.submitted[1][0] == 210.0  # 60 + 2.5 * 60
    assert record['actions'][0]['actual_pulse_time_s'] == 210.0
    assert record['actions'][0]['accepted'] is True
    assert record['samples'][0]['time_min'] == arrival
    assert record['samples'][-1]['time_min'] == 120.0
    at_action = [s['phase'] for s in record['samples'] if s['pulse_time_s'] == 210.0]
    assert at_action == ['sample', 'before_action', 'after_action']
    assert record['engine_failure'] is None and record['reached_horizon']
    result = outcomes.patient_outcome(record)
    assert result['integral_CO_L'] == (120 - arrival) * 5
    assert result['injected_actions'] == result['accepted_actions'] == 1


def test_unadaptable_injury_does_not_initialize_engine(tmp_path):
    engine = ObservedFake('P08')
    record = bridge.execute_patient(spec('P08'), [], tmp_path, native=True, engine=engine)
    assert not engine.initialized and engine.advances == []
    assert record['injury_unsupported']['status'] == 'INJURY_UNSUPPORTED'
    assert 'Dehydration' in record['injury_unsupported']['detail']
    result = outcomes.patient_outcome(record)
    assert result['window_status'] == 'not_simulated'
    assert result['integral_CO_L'] is result['observed_integral_CO_L'] is None


def test_unadaptable_action_is_recorded_and_patient_continues(tmp_path, monkeypatch):
    def unavailable(*args):
        raise ValueError('No adapter for this test action')
    monkeypatch.setattr(bridge, 'treatment_payload', unavailable)
    engine = ObservedFake('P01')
    record = bridge.execute_patient(spec(), [action()], tmp_path, native=True, engine=engine)
    assert len(engine.submitted) == 1  # only the injury
    assert record['actions'][0]['status'] == 'ACTION_UNSUPPORTED'
    assert record['actions'][0]['actual_pulse_time_s'] is None
    assert record['actions'][0]['injected'] is False
    assert record['treatment_incomplete'] and record['reached_horizon']
    result = outcomes.patient_outcome(record)
    assert result['window_status'] == 'complete' and result['integral_CO_L'] == 600
    assert result['unsupported_actions'] == 1 and not result['engine_failure']


def test_native_rejection_is_not_inferred_accepted_from_payload(tmp_path):
    class RejectTreatment(ObservedFake):
        def submit(self, payload):
            super().submit(payload)
            return len(self.submitted) == 1  # injury accepted, treatment rejected
    engine = RejectTreatment('P01')
    record = bridge.execute_patient(spec(), [action()], tmp_path, native=True, engine=engine)
    receipt = record['actions'][0]
    assert receipt['injected'] and receipt['accepted'] is False
    assert receipt['status'] == 'ACTION_UNSUPPORTED' and record['reached_horizon']
    result = outcomes.patient_outcome(record)
    assert result['injected_actions'] == 1 and result['accepted_actions'] == 0
    assert result['treatment_incomplete'] and not result['engine_failure']


@pytest.mark.parametrize('event', ['IrreversibleState', 'CardiacArrest', None])
def test_failed_advance_inspects_terminal_before_classifying_failure(tmp_path, event):
    class Interrupted(ObservedFake):
        def __init__(self):
            super().__init__('P01')
            self.pending = []

        def advance(self, target_s):
            super().advance(target_s)
            if target_s >= 180:
                if event:
                    self.pending.append({'event': event, 'active': True, 'pulse_time_s': 180.0})
                return False
            return True

        def events(self):
            events, self.pending = self.pending, []
            return events
    engine = Interrupted()
    record = bridge.execute_patient(spec(), [action(minute=3)], tmp_path, native=False, engine=engine)
    assert max(end for _, end in engine.advances) == 180
    assert record['actions'][0]['injected'] is False
    result = outcomes.patient_outcome(record)
    assert result['observed_integral_CO_L'] == 10.0
    if event:
        assert result['window_status'] == 'complete_terminal'
        assert not result['engine_failure'] and result['integral_CO_L'] == 10.0
        assert result['terminal_event']['time_min'] == 2.0
    else:
        assert result['window_status'] == 'incomplete_engine_failure'
        assert result['engine_failure'] and result['integral_CO_L'] is None


def test_bulk_advance_uses_native_action_once(monkeypatch):
    engine = bridge.NativePulse.__new__(bridge.NativePulse)
    engine.session = SimpleNamespace(_native=SimpleNamespace(_dt=0.02))
    monkeypatch.setattr(engine, 'now', lambda: 60.00000000000378)
    sent = []
    monkeypatch.setattr(engine, 'submit', lambda payload: sent.append(payload) or True)
    assert engine.advance(120.0)
    assert sent == [{'AdvanceTime': {'Time': {'ScalarTime': {'Value': 60.0, 'Unit': 's'}}}}]


def test_native_event_decoder_obeys_omitted_protobuf_defaults():
    engine = bridge.NativePulse.__new__(bridge.NativePulse)
    # This shape caused the long native run to fail at the first Antidiuresis.
    payload = {'Change': [
        {'SimTime': {'ScalarTime': {'Value': 1551.14, 'Unit': 's'}}, 'Active': True},
        {'Event': 'HypovolemicShock', 'SimTime': {'ScalarTime': {'Unit': 's'}}},
        {'Event': 'IrreversibleState', 'SimTime': {'ScalarTime': {'Value': 1800.0, 'Unit': 's'}}, 'Active': True},
    ]}
    engine.engine = SimpleNamespace(pull_events=lambda fmt: json.dumps(payload))
    engine.fmt = None
    assert engine.events() == [
        {'event': 'Antidiuresis', 'active': True, 'pulse_time_s': 1551.14},
        {'event': 'HypovolemicShock', 'active': False, 'pulse_time_s': 0.0},
        {'event': 'IrreversibleState', 'active': True, 'pulse_time_s': 1800.0},
    ]


def test_empty_native_event_buffer_is_valid():
    engine = bridge.NativePulse.__new__(bridge.NativePulse)
    engine.engine = SimpleNamespace(pull_events=lambda fmt: '')
    engine.fmt = None
    assert engine.events() == []


def test_fake_workers_are_in_independent_processes(chain_data, tmp_path):
    cases, _, context, schedule = chain_data
    selected = [cases[0], cases[8]]
    events = timeline.build_timeline(cases, context, schedule)
    execution = bridge.execute_all(selected, events, tmp_path, native=False)
    pids = {record['worker_pid'] for record in execution.values()}
    assert len(pids) == 2 and os.getpid() not in pids
    assert all(record['reached_horizon'] and record['backend'] == 'fake' for record in execution.values())


@pytest.mark.integration
def test_native_bulk_clock_receipt_and_independent_patient_engines(chain_data, tmp_path):
    cases, _, context, schedule = chain_data
    selected = [cases[0], cases[8]]
    events = [e for e in timeline.build_timeline(cases, context, schedule) if e['time_min'] <= 14.0]
    execution = bridge.execute_all(selected, events, tmp_path, native=True, horizon_min=14.0)
    assert len({r['worker_pid'] for r in execution.values()}) == 2
    assert os.getpid() not in {r['worker_pid'] for r in execution.values()}
    for pid, record in execution.items():
        assert record['engine_failure'] is None and record['injury_unsupported'] is None
        assert record['reached_horizon']
        assert record['samples'][-1]['time_min'] == pytest.approx(14.0, abs=1e-6)
        assert record['samples'][-1]['BloodVolume_mL'] > 0
        assert record['samples'][-1]['CardiacOutput_L_min'] > 0
        for receipt in record['actions']:
            assert receipt['accepted'] is True
            expected = timeline.native_time_s(receipt['planned_time_min'], record['arrival_time_min'])
            assert receipt['actual_pulse_time_s'] == pytest.approx(expected, abs=1e-6)
