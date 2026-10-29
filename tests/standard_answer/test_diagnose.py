import pytest

from core301.standard_answer.diagnose import diagnose_unscheduled, DiagnosisPending
from core301.standard_answer.model import StandardModel
from core301.standard_answer.solve import optimize, Parameters
from core301.standard_answer.export import export_schedule
from core301.dispatch.minimal.validation import validate_schedule
from tests.standard_answer.helpers import fake_costs
from tests.standard_answer.test_optimality import tiny_context


def diagnose(context, *, untreated=100, treated=0):
    parameters = Parameters(time_limit_s=15, workers=1)
    costs, no_treatment = fake_costs(context, untreated=untreated, treated=treated)
    model = StandardModel(context, costs, no_treatment)
    solver, _ = optimize(model, parameters)
    diagnoses = diagnose_unscheduled(model, solver, costs, no_treatment, parameters)
    schedule = export_schedule(model, solver, diagnoses)
    assert not validate_schedule(context, schedule)['conflicts']
    return diagnoses


def test_single_category_shortage_and_real_resource_ids():
    context = tiny_context(1)
    context['resources']['inventory']['A']['decompression_kit']['quantity'] = 0
    result = diagnose(context)['P05']
    assert result['reason_code'] == 'resource_shortage'
    assert result['minimal_categories'] == ['inventory']
    assert result['blocking_resources'] == ['A:decompression_kit']
    assert len(result['checks']) == 6


def test_combined_personnel_and_inventory_shortage():
    context = tiny_context(1)
    for person in context['resources']['personnel']:
        if person['location'] == 'A':
            person['status'] = 'unavailable'
    context['resources']['inventory']['A']['decompression_kit']['quantity'] = 0
    result = diagnose(context)['P05']
    assert result['minimal_categories'] == ['personnel', 'inventory']
    assert 'A:decompression_kit' in result['blocking_resources']
    assert any(r.startswith('A-basic') for r in result['blocking_resources'])


def test_virtual_vehicle_preserves_other_decisions_and_needs_crew():
    context = tiny_context(2)
    context['resources']['transport_min']['turnaround'] = 100
    results = diagnose(context)
    assert len(results) == 1
    result = next(iter(results.values()))
    assert result['minimal_categories'] == ['vehicles', 'personnel']
    assert 'V1' in result['blocking_resources']
    assert 'V1-driver-1' in result['blocking_resources']
    # The solver can choose virtual facility staff even when the originals are
    # free; such incidental choices are not actual bottlenecks.
    assert all(r.startswith('V1') for r in result['blocking_resources'])


def test_all_resources_still_cannot_meet_horizon():
    context = tiny_context(1)
    for origin in context['resources']['travel_min']:
        for destination in context['resources']['travel_min'][origin]:
            if origin != destination:
                context['resources']['travel_min'][origin][destination] = 100
    result = diagnose(context)['P05']
    assert result['reason_code'] == 'time_window_insufficient'
    assert result['blocking_resources'] == []
    assert result['checks'][-1]['status'] == 'INFEASIBLE'


def test_feasible_treatment_worsens_objective_stops_export():
    with pytest.raises(DiagnosisPending, match='可行但会使前两级目标变差') as error:
        diagnose(tiny_context(1), untreated=0, treated=10)
    assert error.value.checks['P05']['checks'][0]['patient_objective'] == [0, 10]
