"""Fixed-decision insertion checks with explicit virtual resource copies."""
import copy
from fractions import Fraction

from ortools.sat.python import cp_model

from core301.dispatch.minimal.api import requirement
from .model import StandardModel
from .solve import new_solver, stage_record

CATEGORIES = ('vehicles', 'personnel', 'equipment', 'space', 'inventory')


class DiagnosisPending(RuntimeError):
    def __init__(self, message, checks):
        super().__init__(message)
        self.checks = checks


class InsertionImprovement(RuntimeError):
    def __init__(self, values, checks):
        self.values, self.checks = values, checks


def virtual_context(context, target, categories):
    """Copies are diagnostic only; original decisions/IDs remain available unchanged.

    A virtual vehicle shares its original onboard resources unless those resource
    categories are also relaxed. In particular it does not supply free extra crew.
    """
    result = copy.deepcopy(context)
    r, original = result['resources'], context['resources']
    virtual_to_original = {}
    copies = {}
    for category, keys in [('personnel', ('personnel',)), ('equipment', ('equipment', 'service_capacities')),
                           ('space', ('spaces',))]:
        if category not in categories:
            continue
        for key in keys:
            for asset in original.get(key, []):
                clone = copy.deepcopy(asset)
                clone.update(id='virtual-' + asset['id'], status='available', available_from_min=0,
                             bound_patient_id=None, _diagnostic_clone=True)
                r[key].append(clone)
                copies[asset['id']] = clone['id']
                r.setdefault('_diagnostic_' + category + '_copies', {})[asset['id']] = clone['id']
                virtual_to_original[clone['id']] = (category, [a['id'] for a in original[key]
                    if a['location'] == asset['location'] and a.get('type', a.get('role')) == asset.get('type', asset.get('role'))])
    if 'vehicles' in categories:
        aliases = r.setdefault('_diagnostic_location_aliases', {})
        for vid, vehicle in original['vehicles'].items():
            clone = copy.deepcopy(vehicle)
            clone_id = 'virtual-' + vid
            clone['crew'] = [copies.get(crew, crew) for crew in vehicle['crew']]
            stretcher = next(s['id'] for s in original['spaces'] if s['location'] == vid and s['type'] == 'stretcher')
            clone['_diagnostic_stretcher'] = copies.get(stretcher, stretcher)
            clone.update(status='available')
            r['vehicles'][clone_id] = clone
            aliases[clone_id] = vid
            # Stock stays shared unless the inventory category is relaxed.
            r['inventory'][clone_id] = r['inventory'][vid]
            virtual_to_original[clone_id] = ('vehicles', [v for v, a in original['vehicles'].items()
                if a['type'] == vehicle['type'] and a['location'] == vehicle['location']])
    if 'inventory' in categories:
        target_patient = next(p for p in context['patients'] if p['patient_id'] == target)
        extra = {}
        for plan in target_patient['candidate_plans']:
            for action in plan['actions']:
                rule = requirement(context['action_mapping'], action, access_mode='new', mode='start')
                for item, count in rule['consumables'].items():
                    extra[item] = extra.get(item, 0) + count
                for item in rule['bulk_resources']:
                    protocol = context['action_mapping']['bulk_protocols'][item]
                    count = protocol.get('reservation_quantity') or 120 * (protocol['rate'] or 0)
                    extra[item] = extra.get(item, 0) + count
        # A single target cannot consume more than the sum of all its candidate courses.
        seen = set()
        for stock in r['inventory'].values():
            if id(stock) in seen:
                continue
            seen.add(id(stock))
            for item, entry in stock.items():
                if entry['quantity'] is not None:
                    entry['quantity'] += extra.get(item, 0)
    return result, virtual_to_original


def diagnose_unscheduled(model, solver, costs, untreated, parameters):
    values, results = model.values(solver), {}
    for pid in model.patients:
        if solver.Value(model.selected[pid]):
            continue
        checks, cache = [], {}

        def attempt(categories):
            key = tuple(c for c in CATEGORIES if c in categories)
            if key in cache:
                return cache[key]
            context, virtual_map = virtual_context(model.context, pid, key)
            trial = StandardModel(context, costs, untreated, max_followup_gap=model.gap, diagnostic_patient=pid,
                                  fixed_values={other: v for other, v in values.items() if other != pid})
            trial.fix_other_patients(values, pid)
            # New resources may be used only by the insertion target.
            # Vehicle aliases share inventory with the original vehicle.
            for alias, original in trial.aliases.items():
                for (location, item), terms in list(trial.spending.items()):
                    if location == alias:
                        trial.spending[original, item].extend(terms)
            trial._inventory()
            weight = max([untreated[pid].deficit10] + [max(costs[pid, plan][1]) for plan in trial.plans[pid]]) + 1
            trial.cp.Minimize(weight * trial.deaths[pid] + trial.deficits[pid])
            engine = new_solver(parameters)
            status = engine.Solve(trial.cp)
            entry = stage_record(engine, status, 'fixed_decision_insertion')
            entry['relaxed_categories'] = list(key)
            entry['virtual_resources_used'] = []
            entry['blocking_resources'] = []
            feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
            if feasible:
                entry['_values'] = trial.values(engine) if not key else None
                entry['patient_objective'] = [engine.Value(trial.deaths[pid]), engine.Value(trial.deficits[pid])]
                used = {h.resource for h in trial.holds if h.patient == pid and h.resource in virtual_map and engine.Value(h.present)}
                entry['virtual_resources_used'] = sorted(used)
                blockers = {rid for resource in used for rid in virtual_map[resource][1]}
                if 'inventory' in key:
                    for (location, item), terms in trial.spending.items():
                        if location in trial.aliases:
                            continue
                        stock = model.r['inventory'].get(location, {}).get(item)
                        if stock and stock['quantity'] is not None:
                            total = sum(coefficient * engine.Value(variable) for coefficient, variable in terms)
                            if total > Fraction(str(stock['quantity'])) - Fraction(str(stock.get('reserved', 0))):
                                blockers.add(location + ':' + item)
                entry['blocking_resources'] = sorted(blockers)
            checks.append(entry)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.INFEASIBLE):
                results[pid] = dict(checks=checks, pending='Insertion feasibility not decided within time limit')
                raise DiagnosisPending(f'{pid}: insertion diagnosis is {engine.StatusName(status)}, not an infeasibility proof', results)
            cache[key] = (feasible, entry)
            return cache[key]

        feasible, baseline = attempt(())
        if feasible:
            previous = [untreated[pid].death, untreated[pid].deficit10]
            message = ('可行但会使前两级目标变差' if baseline['patient_objective'] > previous else
                       '加入可行且目标不差，但阶段三未排入；需要继续求解而不能声明资源不足')
            results[pid] = dict(checks=checks, pending=message)
            if baseline['patient_objective'] <= previous:
                values = baseline.pop('_values')
                raise InsertionImprovement(values, results)
            baseline.pop('_values', None)
            raise DiagnosisPending(f'{pid}: {message}', results)
        successful = []
        for category in CATEGORIES:
            possible, entry = attempt((category,))
            if possible:
                successful.append((category, entry))
        if successful:
            categories = [successful[0][0]]
            certificate = successful[0][1]
        else:
            possible, certificate = attempt(CATEGORIES)
            if not possible:
                results[pid] = dict(reason_code='time_window_insufficient', blocking_resources=[],
                                    checks=checks, minimal_categories=[])
                continue
            categories = []
            for category in CATEGORIES:
                categories.append(category)
                possible, certificate = attempt(categories)
                if possible:
                    break
            for category in list(categories):
                reduced = [c for c in categories if c != category]
                possible, entry = attempt(reduced)
                if possible:
                    categories, certificate = reduced, entry
        if not certificate['blocking_resources']:
            results[pid] = dict(checks=checks, pending='No actual virtual-resource use in capacity certificate')
            raise DiagnosisPending(f'{pid}: no resource bottleneck certificate', results)
        results[pid] = dict(reason_code='resource_shortage', blocking_resources=certificate['blocking_resources'],
                            checks=checks, minimal_categories=categories)
        for check in checks:
            check.pop('_values', None)
    return results
