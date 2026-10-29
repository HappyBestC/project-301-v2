"""Lexicographic optimization; solver status is never upgraded to a proof."""
from dataclasses import asdict, dataclass
import math

import ortools
from ortools.sat.python import cp_model


@dataclass(frozen=True)
class Parameters:
    time_limit_s: float = 600
    workers: int = 8
    seed: int = 0
    max_followup_gap: int = 0

    def __post_init__(self):
        if not math.isfinite(self.time_limit_s) or self.time_limit_s <= 0 or self.workers < 1 or self.max_followup_gap < 0:
            raise ValueError('Invalid solver parameters')


def new_solver(parameters):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = parameters.time_limit_s
    solver.parameters.num_search_workers = parameters.workers
    solver.parameters.random_seed = parameters.seed
    # The optional resource/route model has large symmetry/probing graphs.
    # Disable those preprocessing heuristics; this does not relax constraints.
    solver.parameters.cp_model_probing_level = 0
    solver.parameters.symmetry_level = 0
    return solver


def stage_record(solver, status, name):
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    value, bound = (solver.ObjectiveValue(), solver.BestObjectiveBound()) if feasible else (None, None)
    return dict(name=name, status=solver.StatusName(status), objective=value, best_bound=bound,
                absolute_gap=abs(value - bound) if feasible else None,
                relative_gap=abs(value - bound) / max(1, abs(value)) if feasible else None,
                wall_time_s=solver.WallTime(), optimality_proven=status == cp_model.OPTIMAL)


def hint_decisions(model, values):
    model.cp.ClearHints()
    for pid, decisions in values.items():
        for name, value in decisions.items():
            if name in model.decisions[pid]:
                model.cp.AddHint(model.decisions[pid][name], value)


def complete_hint(model, parameters):
    """Fill auxiliary circuit/order variables for a validated partial incumbent."""
    solver = new_solver(parameters)
    solver.parameters.fix_variables_to_their_hinted_value = True
    status = solver.Solve(model.cp)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        model.cp.ClearHints()
        for index in range(len(model.cp.Proto().variables)):
            variable = model.cp.GetIntVarFromProtoIndex(index)
            model.cp.AddHint(variable, solver.Value(variable))
    else:
        # A warm start is optional, and never changes feasibility or objectives.
        model.cp.ClearHints()
    return dict(status=solver.StatusName(status), wall_time_s=solver.WallTime())


def insertion_seed(model, costs, untreated, parameters):
    """Supply an incumbent; all three objective stages still run unchanged."""
    empty = model.cp.Clone()
    for chosen in model.selected.values():
        empty.Add(chosen == 0)
    solver = new_solver(parameters)
    status = solver.Solve(empty)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []
    values, records = model.values(solver), []
    order = sorted(model.patients, key=lambda p: (-untreated[p].death, -untreated[p].deficit10, p))
    for pid in order:
        trial = type(model)(model.context, costs, untreated, max_followup_gap=model.gap,
            diagnostic_patient=pid, fixed_values={p: v for p, v in values.items() if p != pid})
        trial.cp.Add(trial.selected[pid] == 1)
        weight = max([untreated[pid].deficit10] + [max(costs[pid, p][1]) for p in trial.plans[pid]]) + 1
        trial.cp.Minimize(weight * trial.deaths[pid] + trial.deficits[pid])
        solver = new_solver(parameters)
        status = solver.Solve(trial.cp)
        accepted = False
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            actual = (solver.Value(trial.deaths[pid]), solver.Value(trial.deficits[pid]))
            if actual <= (untreated[pid].death, untreated[pid].deficit10):
                values = trial.values(solver)
                accepted = True
        records.append(dict(patient_id=pid, status=solver.StatusName(status), accepted=accepted, wall_time_s=solver.WallTime()))
    hint_decisions(model, values)
    records.append(dict(auxiliary_hint=complete_hint(model, parameters)))
    return records


def optimize(model, parameters, on_stage=None):
    records, last = [], None
    hint = model.cp.Proto().solution_hint
    incumbent = dict(zip(hint.vars, hint.values)) if len(hint.vars) == len(model.cp.Proto().variables) else None
    def objective_tuple(values):
        return (sum(values[v.Index()] for v in model.deaths.values()),
                sum(values[v.Index()] for v in model.deficits.values()),
                -sum(values[v.Index()] for v in model.selected.values()))
    for name, objective, maximize in [('deaths', model.total_deaths, False),
                                       ('deficit10', model.total_deficit10, False),
                                       ('scheduled', model.total_scheduled, True)]:
        if incumbent is not None:
            known = objective_tuple(incumbent)
            if name == 'deaths': model.cp.Add(objective <= known[0])
            elif name == 'deficit10': model.cp.Add(objective <= known[1])
            else: model.cp.Add(objective >= -known[2])
        (model.cp.Maximize if maximize else model.cp.Minimize)(objective)
        solver = new_solver(parameters)
        status = solver.Solve(model.cp)
        records.append(stage_record(solver, status, name))
        if on_stage:
            on_stage(records)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Keep earlier evidence, but do not export an unfinished three-stage run.
            last = None
            break
        last = solver
        if not maximize:
            # The spec permits an incumbent death bound after a FEASIBLE first stage.
            # Stage three fixes both actual objective values from stage two.
            if name == 'deaths':
                model.cp.Add(objective <= solver.Value(objective))
            else:
                model.cp.Add(model.total_deaths == solver.Value(model.total_deaths))
                model.cp.Add(model.total_deficit10 == solver.Value(model.total_deficit10))
        candidate = {i: solver.Value(model.cp.GetIntVarFromProtoIndex(i)) for i in range(len(model.cp.Proto().variables))}
        if incumbent is None or objective_tuple(candidate) <= objective_tuple(incumbent):
            incumbent = candidate
        # A first-stage solution can have an arbitrarily bad secondary cost.
        # Retain the better feasible seed rather than losing it between stages.
        model.cp.ClearHints()
        for index in range(len(model.cp.Proto().variables)):
            variable = model.cp.GetIntVarFromProtoIndex(index)
            model.cp.AddHint(variable, incumbent[index])
    result = dict(stages=records, parameters=asdict(parameters), ortools_version=ortools.__version__,
                  preprocessing=dict(cp_model_probing_level=0, symmetry_level=0),
                  deaths_optimality_proven=records[0]['optimality_proven'],
                  lexicographic_optimality_proven=len(records) == 3 and all(r['optimality_proven'] for r in records))
    if last is not None:
        result['objective'] = dict(deaths=last.Value(model.total_deaths), deficit10=last.Value(model.total_deficit10),
                                   scheduled=last.Value(model.total_scheduled))
    return last, result
