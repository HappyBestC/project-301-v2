import copy
from itertools import permutations, product

from core301.dispatch.minimal.api import requirement
from core301.standard_answer.model import StandardModel
from core301.standard_answer.solve import Parameters, optimize
from core301.standard_answer.tables import Cost
from core301.standard_answer.export import export_schedule
from core301.dispatch.minimal.validation import validate_schedule
from tests.standard_answer.helpers import context_for


def tiny_context(count=3):
    context = context_for('P05', 'P10', 'P11')
    context['patients'] = context['patients'][:count]
    r = context['resources']
    r['nodes'] = {k: v for k, v in r['nodes'].items() if k in ('A', 'F1', 'F2')}
    r['vehicles'] = {'V1': r['vehicles']['V1']}
    r['travel_min'] = {a: {b: 0 for b in r['nodes']} for a in r['nodes']}
    for key in ('personnel', 'equipment', 'spaces', 'service_capacities'):
        r[key] = [a for a in r[key] if a['location'] in ('A', 'V1')]
    r['inventory'] = {key: stock for key, stock in r['inventory'].items() if key in ('A', 'V1')}
    for stock in r['inventory'].values():
        for value in stock.values():
            value['quantity'] = 10000
    for patient in context['patients']:
        patient['arrival_time_min'] = 0
    return context


def test_exhaustive_vehicle_order_and_plan_choice_matches_three_stages():
    context = tiny_context()
    costs, untreated = {}, {}
    for i, patient in enumerate(context['patients']):
        pid = patient['patient_id']
        first = patient['candidate_plans'][0]
        second = copy.deepcopy(first)
        second['plan_id'] = pid + '-plan-2'
        second['actions'][0].update(action_id=pid + '-plan-2-a1', action_type='occlusive_dressing')
        patient['candidate_plans'].append(second)
        for j, plan in enumerate(patient['candidate_plans']):
            threshold = (25, 12, 30)[i] + j * 15
            costs[pid, plan['plan_id']] = ([int(e > threshold) for e in range(121)],
                [(3-i) * e + 30*j for e in range(121)])
        untreated[pid] = Cost(1, 1000, 60, False, ('untreated',))
    ids = [p['patient_id'] for p in context['patients']]
    by_id = {p['patient_id']: p for p in context['patients']}
    best = None
    for count in range(len(ids) + 1):
        for order in permutations(ids, count):
            for choices in product((0, 1), repeat=count):
                deaths = len(ids) - count
                deficit = (len(ids) - count) * 10000
                available = 0
                for pid, choice in zip(order, choices):
                    plan = by_id[pid]['candidate_plans'][choice]
                    rule = requirement(context['action_mapping'], plan['actions'][0])
                    duration = rule['duration_min']
                    # Independent earliest-time enumeration: load 3, handoff 5, turnaround 5.
                    onboard = 'basic_ambulance' in rule['allowed_start'] and duration <= 8
                    effect = available + (0 if onboard else 3 + 5) + duration
                    available += 3 + 5 + 5
                    ds, cs = costs[pid, plan['plan_id']]
                    deaths += ds[effect]
                    deficit += cs[effect]
                objective = deaths, deficit, -count
                if best is None or objective < best:
                    best = objective
    model = StandardModel(context, costs, untreated)
    solver, report = optimize(model, Parameters(time_limit_s=20, workers=1))
    actual = report['objective']
    assert (actual['deaths'], actual['deficit10'], -actual['scheduled']) == best
    assert report['lexicographic_optimality_proven']
    assert validate_schedule(context, export_schedule(model, solver))['conflicts'] == []


def test_third_stage_schedules_zero_benefit_patients():
    context = tiny_context(1)
    pid = context['patients'][0]['patient_id']
    plan = context['patients'][0]['candidate_plans'][0]['plan_id']
    model = StandardModel(context, {(pid, plan): ([0]*121, [0]*121)}, {pid: Cost(0, 0, None, False, ('untreated',))})
    _, report = optimize(model, Parameters(time_limit_s=10, workers=1))
    assert report['objective'] == dict(deaths=0, deficit10=0, scheduled=1)
    assert len(report['stages']) == 3
