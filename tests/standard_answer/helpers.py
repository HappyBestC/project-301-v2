import copy
import csv
from io import StringIO

from core301.standard_answer.scenario import load_scenario
from core301.standard_answer.tables import Cost, group_id, plan_key
from core301.standard_answer.model import StandardModel
from core301.standard_answer.solve import Parameters, new_solver
from core301.standard_answer.export import export_schedule
from ortools.sat.python import cp_model


def context_for(*ids):
    context, specs, typical, definition = load_scenario()
    if ids:
        context['patients'] = [p for p in context['patients'] if p['patient_id'] in ids]
    return context


def fake_costs(context, *, treated=0, untreated=100):
    costs, no_treatment = {}, {}
    for patient in context['patients']:
        pid = patient['patient_id']
        for plan in patient['candidate_plans']:
            count = 121 - int(patient['arrival_time_min'])
            costs[pid, plan['plan_id']] = ([0] * count, [treated] * count)
        no_treatment[pid] = Cost(0, untreated, None, False, ('untreated',))
    return costs, no_treatment


def make_model(context, **kwargs):
    costs, untreated = fake_costs(context)
    return StandardModel(context, costs, untreated, **kwargs)


def solve_model(model, *, feasible=True, seconds=15):
    solver = new_solver(Parameters(time_limit_s=seconds, workers=1))
    status = solver.Solve(model.cp)
    if feasible:
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), solver.StatusName(status)
    else:
        assert status == cp_model.INFEASIBLE, solver.StatusName(status)
    return solver


def scheduled(pid, plan_number=1, *, onboard=False):
    context = context_for(pid)
    if onboard:
        context['resources']['inventory']['V1']['oxygen']['quantity'] = 100
    model = make_model(context)
    plan = next(p for p in context['patients'][0]['candidate_plans'] if p['plan_id'] == f'{pid}-plan-{plan_number}')
    model.cp.Add(model.plans[pid][plan['plan_id']] == 1)
    model.cp.Add(model.trips[pid]['options']['V1', 'H1'] == 1)
    arrival = int(context['patients'][0]['arrival_time_min'])
    model.cp.Add(model.trips[pid]['start'] == arrival)
    first = model.operations[plan['actions'][0]['action_id']]
    if onboard:
        model.cp.Add(first.locations['V1'] == 1)
        model.cp.Add(first.end == 30)
    else:
        model.cp.Add(first.locations['H1'] == 1)
        model.cp.Add(first.start == model.trips[pid]['handoff'])
    solver = solve_model(model)
    return context, model, solver, export_schedule(model, solver)


def table_text(points, *, window_bad=None):
    summary, cumulative = StringIO(), StringIO()
    fields = ['d', 'source', 'window_status', 'terminal_min']
    writer = csv.DictWriter(summary, fields)
    writer.writeheader()
    series = csv.writer(cumulative)
    series.writerow(['d'] + [f'm{i}' for i in range(121)])
    for d, terminal, multiplier, source, status in points:
        writer.writerow(dict(d=d, source=source, window_status=status, terminal_min=terminal))
        series.writerow([d] + [i * multiplier if i != window_bad else '' for i in range(121)])
    return summary.getvalue(), cumulative.getvalue()


def write_fake_tables(directory, context=None, specs=None, *, delay_dependent=False):
    if context is None:
        context, specs, *_ = load_scenario()
    directory.mkdir(parents=True, exist_ok=True)
    points = [('untreated', None, 1, 'run', 'complete')] + [(d, None, d / 1200 if delay_dependent else 0, 'run', 'complete') for d in range(121)]
    summary, cumulative = table_text(points)
    for patient in context['patients']:
        for plan in patient['candidate_plans']:
            name = group_id(specs[patient['patient_id']]) + '__' + plan_key(plan)
            (directory / (name + '.csv')).write_text(summary)
            (directory / (name + '__cum_deficit_L.csv')).write_text(cumulative)
    return directory
