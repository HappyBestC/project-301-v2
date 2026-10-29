import copy
import csv
import json

from core301.standard_answer.verify import compare, verify_run, write_json
from core301.standard_answer.export import export_schedule
from core301.standard_answer.model import StandardModel
from core301.standard_answer.solve import optimize, Parameters
from tests.standard_answer.helpers import fake_costs
from tests.standard_answer.test_optimality import tiny_context


def test_interpolated_terminal_difference_reported_without_failure():
    predicted = {'patients': [dict(patient_id='P01', death=1, terminal_global_min=70,
                                   deficit_L=100, interpolated=True)]}
    measured = {'P01': dict(complete=True, death=1, terminal_global_min=80, deficit_L=102,
                            followup_deviations_min=[])}
    result = compare(predicted, measured)
    assert result['consistent']
    assert result['patients'][0]['terminal_difference_min'] == 10
    predicted['patients'][0]['interpolated'] = False
    assert not compare(predicted, measured)['consistent']
    predicted['patients'][0]['interpolated'] = True
    measured['P01']['death'] = 0
    assert not compare(predicted, measured)['consistent']
    measured['P01']['death'] = 1
    measured['P01']['deficit_L'] = 102.01
    result = compare(predicted, measured)
    assert not result['consistent']
    assert '插值' in result['patients'][0]['possible_causes'][0]


def test_execution_failure_never_counts_as_survival_or_consistency():
    predicted = {'patients': [dict(patient_id='P01', death=0, terminal_global_min=None,
                                   deficit_L=0, interpolated=False)]}
    measured = {'P01': dict(complete=False, death=0, terminal_global_min=None, deficit_L=None,
                            followup_deviations_min=[])}
    result = compare(predicted, measured)
    assert not result['consistent']
    assert result['measured_deficit_L'] is None


def test_verify_passes_all_cases_to_native_bridge_with_true_specs(tmp_path, monkeypatch):
    from core301.agent_chain import bridge
    from core301.standard_answer.scenario import load_scenario
    context = tiny_context(2)
    costs, untreated = fake_costs(context)
    model = StandardModel(context, costs, untreated)
    solver, _ = optimize(model, Parameters(time_limit_s=15, workers=1))
    schedule = export_schedule(model, solver)
    # Make one casualty unscheduled; it must still go to Pulse.
    pid = context['patients'][1]['patient_id']
    schedule['selections'].pop(pid)
    for key in ('transports', 'operations', 'care'):
        schedule[key] = [t for t in schedule[key] if t['patient_id'] != pid]
    schedule['patient_results'][1] = dict(patient_id=pid, status='unscheduled', reason_code='resource_shortage',
        reason='在最优排程中资源分配给了其他伤员，车辆资源不能同时服务。',
        blocking_resources=['V1'], considered_alternatives=[pid + '-plan-1'])
    specs = load_scenario()[1]
    selected_specs = [dict(specs[p['patient_id']], arrival_time_min=0) for p in context['patients']]
    prediction = {'patients': [dict(patient_id=p['patient_id'], death=0, terminal_global_min=None,
        deficit_L=0, interpolated=False) for p in context['patients']]}
    for name, value in [('context', context), ('schedule', schedule), ('patient_specs', selected_specs), ('prediction', prediction)]:
        write_json(tmp_path / (name + '.json'), value)
    reference = tmp_path / 'reference'
    reference.mkdir()
    with (reference / 'samples.csv').open('w') as handle:
        writer = csv.DictWriter(handle, ['time_min', 'CardiacOutput_L_min'])
        writer.writeheader()
        writer.writerows(dict(time_min=i, CardiacOutput_L_min=5) for i in range(121))
    def fake_execution(cases, timeline, run_dir, *, native, horizon_min, dataset_dir):
        assert native is True and horizon_min == 120
        actual_specs = json.loads((dataset_dir / 'patient_specs.json').read_text())
        assert actual_specs == selected_specs
        assert len(cases) == 2 and len([t for t in timeline if t['event'] == 'injury_onset']) == 2
        return {s['patient_id']: bridge.execute_patient(s, timeline, run_dir / s['patient_id'], native=False) for s in actual_specs}
    monkeypatch.setattr(bridge, 'execute_all', fake_execution)
    assert verify_run(tmp_path, reference_dir=reference)['consistent']
    assert (tmp_path / 'comparison.json').exists()
