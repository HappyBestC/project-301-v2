"""CP-SAT model of the V1 validator's half-open resource reservations."""
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
import math

from ortools.sat.python import cp_model

from core301.dispatch.minimal.api import requirement


def integer(value):
    if not math.isfinite(value) or int(value) != value:
        raise ValueError(f'V1 requires integral scheduler minutes: {value}')
    return int(value)


@dataclass
class Hold:
    resource: str
    patient: str
    task: str
    kind: str
    start: object
    end: object
    present: object
    interval: object


@dataclass
class Operation:
    patient: str
    plan: str
    action: dict
    rule: dict
    present: object
    start: object
    end: object
    locations: dict = field(default_factory=dict)
    staff: list = field(default_factory=list)
    access_staff: dict = field(default_factory=dict)
    equipment: list = field(default_factory=list)
    spaces: dict = field(default_factory=dict)
    support_spaces: dict = field(default_factory=dict)
    care: list = field(default_factory=list)


class StandardModel:
    def __init__(self, context, costs, untreated, *, max_followup_gap=0,
                 diagnostic_patient=None, fixed_values=None):
        self.context, self.r = context, context['resources']
        self.aliases = self.r.get('_diagnostic_location_aliases', {})
        self.mapping = context['action_mapping']
        self.horizon = integer(context['horizon_min'])
        if self.horizon != 120 or type(max_followup_gap) is not int or max_followup_gap < 0:
            raise ValueError('V1 requires horizon 120 and a nonnegative integer follow-up gap')
        self.gap, self.diagnostic_patient = max_followup_gap, diagnostic_patient
        self.fixed_values = fixed_values or {}
        self.cp = cp_model.CpModel()
        self.decisions = defaultdict(dict)
        self.holds, self.spending = [], defaultdict(list)
        self.patients = {p['patient_id']: p for p in context['patients']}
        self.assets = {a['id']: a for k in ('personnel', 'equipment', 'spaces', 'service_capacities')
                       for a in self.r.get(k, [])}
        self.spaces = {a['id']: a for a in self.r['spaces']}
        self.people = {a['id']: a for a in self.r['personnel']}
        self.selected, self.plans, self.trips, self.operations = {}, {}, {}, {}
        self.deaths, self.deficits = {}, {}
        for pid, patient in self.patients.items():
            chosen = self.boolean(pid, 'scheduled')
            self.selected[pid] = chosen
            ps = {p['plan_id']: self.boolean(pid, p['plan_id']) for p in patient['candidate_plans']}
            self.plans[pid] = ps
            self.cp.Add(sum(ps.values()) == chosen)
            self._trip(pid)
            for plan in patient['candidate_plans']:
                self._plan(pid, plan)
            self._cost(pid, costs, untreated[pid])
        self._routes()
        self._occupancy()
        self._inventory()
        self.total_deaths = sum(self.deaths.values())
        self.total_deficit10 = sum(self.deficits.values())
        self.total_scheduled = sum(self.selected.values())

    def boolean(self, pid, name):
        variable = (self.cp.NewConstant(self.fixed_values[pid].get(name, 0)) if pid in self.fixed_values
                    else self.cp.NewBoolVar(f'{pid}/{name}'))
        self.decisions[pid][name] = variable
        return variable

    def minute(self, pid, name, low=0, high=120):
        variable = (self.cp.NewConstant(self.fixed_values[pid].get(name, 0)) if pid in self.fixed_values
                    else self.cp.NewIntVar(low, high, f'{pid}/{name}'))
        self.decisions[pid][name] = variable
        return variable

    def both(self, *literals):
        present = self.cp.NewBoolVar('and')
        self.cp.AddBoolAnd(literals).OnlyEnforceIf(present)
        self.cp.AddBoolOr([x.Not() for x in literals]).OnlyEnforceIf(present.Not())
        return present

    def _choice(self, choices, rid, chosen):
        if rid in choices:
            combined = self.cp.NewBoolVar('resource_at_either_alias')
            self.cp.Add(combined == choices[rid] + chosen)
            choices[rid] = combined
        else:
            choices[rid] = chosen

    def _usable(self, rid, pid, present, start, location):
        asset = self.assets[rid]
        if asset['location'] != self.aliases.get(location, location) or asset.get('status') != 'available' or asset.get('bound_patient_id') not in (None, pid):
            self.cp.Add(present == 0)
        else:
            self.cp.Add(start >= integer(asset.get('available_from_min', 0))).OnlyEnforceIf(present)

    def hold(self, rid, pid, task, kind, start, end, present, *, location=None):
        if list(present.Proto().domain) == [0, 0]:
            return
        if location is not None:
            self._usable(rid, pid, present, start, location)
        size = self.cp.NewIntVar(0, 10000, 'hold_size')
        self.cp.Add(size == end - start).OnlyEnforceIf(present)
        interval = self.cp.NewOptionalIntervalVar(start, size, end, present, f'{rid}:{task}:{kind}')
        self.holds.append(Hold(rid, pid, task, kind, start, end, present, interval))

    def _trip(self, pid):
        patient, chosen = self.patients[pid], self.selected[pid]
        trip = {k: self.minute(pid, 'trip/' + k) for k in ('start', 'load', 'depart', 'arrive', 'handoff', 'end')}
        trip['origin'] = self.minute(pid, 'trip/origin', 0, len(self.r['nodes']) - 1)
        trip['options'], trip['vehicles'], trip['destinations'] = {}, {}, {}
        self.trips[pid] = trip
        self.cp.Add(trip['start'] >= integer(patient['arrival_time_min'])).OnlyEnforceIf(chosen)
        stages = self.r['transport_min']
        for a, b, length in [('load', 'depart', stages['loading']), ('arrive', 'handoff', stages['handoff']),
                             ('handoff', 'end', stages['turnaround'])]:
            self.cp.Add(trip[b] == trip[a] + integer(length)).OnlyEnforceIf(chosen)
        for v, vehicle in self.r['vehicles'].items():
            has_vehicle = self.boolean(pid, f'trip/vehicle/{v}')
            trip['vehicles'][v] = has_vehicle
            if vehicle['status'] != 'available':
                self.cp.Add(has_vehicle == 0)
            self.cp.Add(trip['start'] >= integer(vehicle.get('available_from_min', 0))).OnlyEnforceIf(has_vehicle)
            options = []
            for destination in ('A', 'B', 'H1', 'H2'):
                if destination not in self.r['nodes']:
                    continue
                # A direct destination must support every action of at least one
                # candidate plan. Removing impossible route nodes is exact.
                if not any(all(self.r['nodes'][destination]['type'] in requirement(self.mapping, a)['allowed_start']
                               for a in plan['actions']) for plan in patient['candidate_plans']):
                    continue
                q = self.boolean(pid, f'trip/{v}/{destination}')
                trip['options'][v, destination] = q
                options.append(q)
                length = integer(self.r['travel_min'][patient['location']][destination])
                self.cp.Add(trip['arrive'] == trip['depart'] + length).OnlyEnforceIf(q)
            self.cp.Add(sum(options) == has_vehicle)
            self.hold(v, pid, f'{pid}-transport', 'vehicle', trip['start'], trip['end'], has_vehicle)
            stretchers = [s for s in self.r['spaces'] if s['location'] == self.aliases.get(v, v) and s['type'] == 'stretcher'
                          and s['id'] == vehicle.get('_diagnostic_stretcher', s['id']) and
                          (not s.get('_diagnostic_clone') or '_diagnostic_stretcher' in vehicle)]
            if vehicle['stretcher_capacity'] != 1 or len(stretchers) != 1:
                self.cp.Add(has_vehicle == 0)
            else:
                stretcher = stretchers[0]['id']
                if pid == self.diagnostic_patient:
                    stretcher = self.r.get('_diagnostic_space_copies', {}).get(stretcher, stretcher)
                self.hold(stretcher, pid, f'{pid}-transport', 'transport_space', trip['load'], trip['handoff'], has_vehicle)
            for crew in vehicle['crew']:
                if pid == self.diagnostic_patient:
                    crew = self.r.get('_diagnostic_personnel_copies', {}).get(crew, crew)
                self.hold(crew, pid, f'{pid}-transport', 'crew', trip['start'], trip['end'], has_vehicle, location=v)
        self.cp.Add(sum(trip['vehicles'].values()) == chosen)
        for destination in ('A', 'B', 'H1', 'H2'):
            if destination not in self.r['nodes']:
                continue
            q = self.boolean(pid, f'trip/destination/{destination}')
            trip['destinations'][destination] = q
            self.cp.Add(sum(p for (v, h), p in trip['options'].items() if h == destination) == q)

    def _routes(self):
        nodes = list(self.r['nodes'])
        travel = self.r['travel_min']
        for vid, vehicle in self.r['vehicles'].items():
            options = [(pid, h, q) for pid, tr in self.trips.items() for (v, h), q in tr['options'].items()
                       if v == vid and list(q.Proto().domain) != [0, 0]]
            arcs = []
            empty = self.cp.NewBoolVar(vid + '/empty')
            self.cp.Add(sum(q for _, _, q in options) == 0).OnlyEnforceIf(empty)
            self.cp.Add(sum(q for _, _, q in options) >= 1).OnlyEnforceIf(empty.Not())
            arcs.append((0, 0, empty))
            for index, (pid, destination, q) in enumerate(options, 1):
                trip = self.trips[pid]
                arcs.append((index, index, q.Not()))
                first = self.cp.NewBoolVar(f'{vid}/first/{index}')
                last = self.cp.NewBoolVar(f'{vid}/last/{index}')
                arcs.extend(((0, index, first), (index, 0, last)))
                origin = vehicle['location']
                self.cp.Add(trip['origin'] == nodes.index(origin)).OnlyEnforceIf(first)
                self.cp.Add(trip['load'] == trip['start'] + integer(travel[origin][self.patients[pid]['location']])).OnlyEnforceIf(first)
                for next_index, (other, _, _) in enumerate(options, 1):
                    if pid == other:
                        continue
                    other_destination = options[next_index - 1][1]
                    pickup = self.patients[pid]['location']
                    stages = self.r['transport_min']
                    origins = {vehicle['location']} | {h for _, h, _ in options}
                    earliest_end = integer(self.patients[pid]['arrival_time_min']) + min(travel[o][pickup] for o in origins)
                    earliest_end += stages['loading'] + travel[pickup][destination] + stages['handoff'] + stages['turnaround']
                    next_length = travel[destination][self.patients[other]['location']] + stages['loading']
                    next_length += travel[self.patients[other]['location']][other_destination] + stages['handoff'] + stages['turnaround']
                    if earliest_end + next_length > 120:
                        continue
                    arc = self.cp.NewBoolVar(f'{vid}/{index}/{next_index}')
                    arcs.append((index, next_index, arc))
                    nxt = self.trips[other]
                    self.cp.Add(nxt['start'] >= trip['end']).OnlyEnforceIf(arc)
                    self.cp.Add(nxt['origin'] == nodes.index(destination)).OnlyEnforceIf(arc)
                    self.cp.Add(nxt['load'] == nxt['start'] + integer(travel[destination][self.patients[other]['location']])).OnlyEnforceIf(arc)
            self.cp.AddCircuit(arcs)

    def _plan(self, pid, plan):
        selected = self.plans[pid][plan['plan_id']]
        actions = plan['actions']
        if not actions:
            raise ValueError('Empty candidate plan')
        # Probe templates are linear; reject a changed template, never invent its offsets.
        if any(a['depends_on'] != ([] if i == 0 else [actions[i - 1]['action_id']]) for i, a in enumerate(actions)):
            raise ValueError(f"Non-linear probe template requires a design decision: {plan['plan_id']}")
        ops = []
        for action in actions:
            rule = requirement(self.mapping, action, access_mode='new', mode='start')
            duration, arrival = integer(rule['duration_min']), integer(self.patients[pid]['arrival_time_min'])
            start = self.minute(pid, action['action_id'] + '/start', arrival, 120 - duration)
            end = self.minute(pid, action['action_id'] + '/end', arrival + duration)
            self.cp.Add(end == start + duration)
            op = Operation(pid, plan['plan_id'], action, rule, selected, start, end)
            self.operations[action['action_id']] = op
            ops.append(op)
            # Every destination must be able to execute the entire plan, even if an action is onboard.
            for h, destination in self.trips[pid]['destinations'].items():
                if self.r['nodes'][h]['type'] not in rule['allowed_start']:
                    self.cp.AddBoolOr([selected.Not(), destination.Not()])
            self._operation(op)
        offset = 0
        by_id = {op.action['action_id']: op for op in ops}
        for i, op in enumerate(ops):
            if i:
                offset += integer(op.rule['duration_min'])
                self.cp.Add(op.end <= ops[0].end + offset + self.gap).OnlyEnforceIf(selected)
            for dependency in op.rule['depends_on']:
                self.cp.Add(by_id[dependency].end <= op.start).OnlyEnforceIf(selected)
            predecessors = list(op.rule['predecessor_actions'])
            injury_pred = op.rule.get('injury_predecessors', {}).get(self.patients[pid]['known_injury_context']['injury_type'])
            if injury_pred:
                predecessors.append(injury_pred)
            for kind in predecessors:
                candidates = [p for p in ops if p.action['action_type'] == kind]
                if not candidates:
                    self.cp.Add(selected == 0)
                else:
                    choices = []
                    for prior in candidates:
                        before = self.cp.NewBoolVar('predecessor')
                        self.cp.Add(prior.end <= op.start).OnlyEnforceIf(before)
                        choices.append(before)
                    self.cp.AddBoolOr(choices).OnlyEnforceIf(selected)
        # Linear action order is guaranteed by the probe templates' dependencies.
        for a, b in zip(ops, ops[1:]):
            for rid in sorted(set(a.spaces) & set(b.spaces)):
                gap = self.both(a.spaces[rid], b.spaces[rid])
                self.hold(rid, pid, a.action['action_id'], 'space', a.end, b.start, gap)

    def _operation(self, op):
        pid, aid, rule = op.patient, op.action['action_id'], op.rule
        trip = self.trips[pid]
        for loc, chosen in (trip['destinations'] | trip['vehicles']).items():
            kind = (self.r['nodes'].get(loc) or self.r['vehicles'].get(loc))['type']
            if kind not in rule['allowed_start']:
                continue
            present = self.boolean(pid, f'{aid}/location/{loc}')
            op.locations[loc] = present
            self.cp.AddImplication(present, chosen)
            if loc in self.r['vehicles']:
                self.cp.Add(op.start >= trip['load']).OnlyEnforceIf(present)
                self.cp.Add(op.end <= trip['handoff']).OnlyEnforceIf(present)
            else:
                self.cp.Add(op.start >= trip['handoff']).OnlyEnforceIf(present)
        self.cp.Add(sum(op.locations.values()) == op.present)
        phase = integer(rule['access_phase_min'])
        op.staff = [self._assign(pid, f'{aid}/staff/{i}', role, op.locations, op.start + phase, op.end, aid)
                    for i, role in enumerate(rule['staff_roles'])]
        for rid in self.people:
            self.cp.Add(sum(slot.get(rid, 0) for slot in op.staff) <= 1)
        if phase:
            op.access_staff = self._assign(pid, f'{aid}/access', rule['access']['role'], op.locations, op.start, op.start + phase, aid)
        equip_end = 120 if rule['continuous'] else op.end + integer(rule['equipment_turnaround_min'])
        op.equipment = [self._equipment(op, kind, i, equip_end) for i, kind in enumerate(rule['equipment'])]
        for rid in (a['id'] for a in self.r['equipment']):
            self.cp.Add(sum(slot.get(rid, 0) for slot in op.equipment) <= 1)
        self._spaces(op)
        for loc, present in op.locations.items():
            for item, quantity in rule['consumables'].items():
                self.spending[loc, item].append((Fraction(quantity), present))
            for bulk in rule['bulk_resources']:
                if rule.get('bulk_resource_scope', {}).get(bulk) == 'out_of_scope_not_modeled_not_zero':
                    continue
                protocol = self.mapping['bulk_protocols'][bulk]
                if protocol.get('reservation_quantity') is not None:
                    self.spending[loc, bulk].append((Fraction(protocol['reservation_quantity']), present))
                elif protocol['rate'] is not None:
                    minutes = self.minute(pid, f'{aid}/stock/{loc}/{bulk}')
                    self.cp.Add(minutes == 120 - op.end).OnlyEnforceIf(present)
                    self.cp.Add(minutes == 0).OnlyEnforceIf(present.Not())
                    self.spending[loc, bulk].append((Fraction(str(protocol['rate'])), minutes))
        if rule['continuous']:
            self._care(op)

    def _assign(self, pid, label, role, locations, start, end, task):
        choices = {}
        for loc, present in locations.items():
            local = []
            for person in self.people.values():
                if person['location'] != self.aliases.get(loc, loc) or role not in person['capabilities']:
                    continue
                rid = person['id']
                chosen = self.boolean(pid, label + '/' + loc + '/' + rid)
                self._choice(choices, rid, chosen)
                local.append(chosen)
                self.hold(rid, pid, task, 'operation', start, end, chosen, location=loc)
            self.cp.Add(sum(local) == present)
        return choices

    def _equipment(self, op, kind, index, end):
        choices = {}
        for loc, present in op.locations.items():
            local = []
            for asset in self.r['equipment']:
                if asset['location'] != self.aliases.get(loc, loc) or asset['type'] != kind:
                    continue
                rid = asset['id']
                chosen = self.boolean(op.patient, f"{op.action['action_id']}/equipment/{index}/{loc}/{rid}")
                self._choice(choices, rid, chosen)
                local.append(chosen)
                self.hold(rid, op.patient, op.action['action_id'], 'equipment', op.start, end, chosen, location=loc)
            self.cp.Add(sum(local) == present)
        return choices

    def _spaces(self, op):
        pid, aid, rule = op.patient, op.action['action_id'], op.rule
        has_support = self.boolean(pid, aid + '/has_support')
        hold_end = self.minute(pid, aid + '/space_end')
        self.cp.Add(hold_end == op.end).OnlyEnforceIf(has_support)
        self.cp.Add(hold_end == (120 if rule['continuous'] else op.end)).OnlyEnforceIf(has_support.Not())
        for loc, present in op.locations.items():
            kind = 'vehicle' if loc in self.r['vehicles'] else self.r['nodes'][loc]['type']
            allowed = rule['space_types'].get(kind, [])
            primary = []
            for rid, asset in self.spaces.items():
                if asset['location'] != self.aliases.get(loc, loc):
                    continue
                if asset['type'] in allowed:
                    chosen = self.boolean(pid, f'{aid}/space/{loc}/{rid}')
                    self._choice(op.spaces, rid, chosen)
                    primary.append(chosen)
                    self.hold(rid, pid, aid, 'space', op.start, hold_end, chosen, location=loc)
                    if rule['continuous'] and asset['type'] == 'treatment':
                        self.cp.AddImplication(chosen, has_support)
                    if rule.get('space_capability'):
                        capabilities = [c for c in self.r.get('service_capacities', [])
                                        if c['location'] == loc and c['type'] == rule['space_capability'] and c['requires_space_type'] == asset['type']]
                        if not capabilities or (len(capabilities) != 1 and self.diagnostic_patient is None):
                            self.cp.Add(chosen == 0)
                        elif len(capabilities) == 1:
                            self.hold(capabilities[0]['id'], pid, aid, 'service_capacity', op.start, op.end, chosen, location=loc)
                        else:
                            assignments = []
                            for capability in capabilities:
                                q = self.cp.NewBoolVar(f'{aid}/capacity/{rid}/{capability["id"]}')
                                if pid != self.diagnostic_patient and capability.get('_diagnostic_clone'):
                                    self.cp.Add(q == 0)
                                assignments.append(q)
                                self.hold(capability['id'], pid, aid, 'service_capacity', op.start, op.end, q, location=loc)
                            self.cp.Add(sum(assignments) == chosen)
                if rule['continuous'] and asset['type'] in rule['support_space_types'].get(kind, []):
                    chosen = self.boolean(pid, f'{aid}/support/{loc}/{rid}')
                    self._choice(op.support_spaces, rid, chosen)
                    self.cp.AddImplication(chosen, present)
                    self.hold(rid, pid, aid, 'space', op.end, 120, chosen, location=loc)
            if allowed:
                self.cp.Add(sum(primary) == present)
        self.cp.Add(sum(op.support_spaces.values()) == has_support)
        self.cp.AddImplication(has_support, op.present)

    def _care(self, op):
        pid, aid, care = op.patient, op.action['action_id'], op.rule['care']
        period, duration = integer(care['period_min']), integer(care['duration_min'])
        trip = self.trips[pid]
        for k in range(1, 120 // period + 1):
            start, end = op.end + k * period, op.end + k * period + duration
            due = self.boolean(pid, f'{aid}/care/{k}/due')
            self.cp.Add(end <= 120).OnlyEnforceIf(due)
            self.cp.Add(end >= 121).OnlyEnforceIf([op.present, due.Not()])
            self.cp.AddImplication(due, op.present)
            locations = {}
            for loc, chosen in (trip['destinations'] | trip['vehicles']).items():
                q = self.boolean(pid, f'{aid}/care/{k}/location/{loc}')
                self.cp.AddImplication(q, chosen)
                if loc in self.r['vehicles']:
                    self.cp.Add(start >= trip['load']).OnlyEnforceIf(q)
                    self.cp.Add(end <= trip['handoff']).OnlyEnforceIf(q)
                else:
                    self.cp.Add(start >= trip['handoff']).OnlyEnforceIf(q)
                locations[loc] = q
            self.cp.Add(sum(locations.values()) == due)
            task = f'{aid}-care-{k}'
            staff = self._assign(pid, task, care['role'], locations, start, end, task)
            op.care.append(dict(present=due, start=start, end=end, locations=locations, staff=staff, task_id=task))

    def _cost(self, pid, costs, untreated):
        max_deficit = max([untreated.deficit10] + [max(costs[pid, p][1]) for p in self.plans[pid]])
        death = self.boolean(pid, 'death')
        deficit = self.minute(pid, 'deficit10', 0, max_deficit)
        self.deaths[pid], self.deficits[pid] = death, deficit
        for plan in self.patients[pid]['candidate_plans']:
            first = self.operations[plan['actions'][0]['action_id']]
            arrival = integer(self.patients[pid]['arrival_time_min'])
            index = self.minute(pid, plan['plan_id'] + '/delay', 0, 120 - arrival)
            self.cp.Add(index == first.end - arrival)
            dv, cv = self.boolean(pid, plan['plan_id'] + '/table_death'), self.minute(pid, plan['plan_id'] + '/table_deficit10', 0, max_deficit)
            ds, cs = costs[pid, plan['plan_id']]
            self.cp.AddElement(index, ds, dv)
            self.cp.AddElement(index, cs, cv)
            self.cp.Add(death == dv).OnlyEnforceIf(first.present)
            self.cp.Add(deficit == cv).OnlyEnforceIf(first.present)
        self.cp.Add(death == untreated.death).OnlyEnforceIf(self.selected[pid].Not())
        self.cp.Add(deficit == untreated.deficit10).OnlyEnforceIf(self.selected[pid].Not())

    def _separate(self, a, b):
        order = self.cp.NewBoolVar('resource_order')
        self.cp.Add(a.end <= b.start).OnlyEnforceIf([a.present, b.present, order])
        self.cp.Add(b.end <= a.start).OnlyEnforceIf([a.present, b.present, order.Not()])

    def _occupancy(self):
        for h in self.r.get('initial_reservations', []):
            self.hold(h['resource_id'], h['patient_id'], h['task_id'], h['kind'],
                      integer(h['start_min']), integer(h['end_min']), self.cp.NewConstant(1))
        groups = defaultdict(list)
        patient_spaces = defaultdict(list)
        for hold in self.holds:
            groups[hold.resource].append(hold)
            if hold.resource in self.spaces and hold.kind != 'transport_space':
                patient_spaces[hold.patient].append(hold)
        for rid, holds in groups.items():
            if rid in self.spaces:
                # In the current linear templates only the last action can be
                # continuous. Primary, gap and support intervals for a patient
                # are therefore disjoint at destinations. NoOverlap is exact
                # and avoids quadratic ordering variables. Keep the general
                # validator-equivalent pairwise form for other templates or
                # initial reservations with possible same-patient overlaps.
                simple = not self.r.get('initial_reservations') and all(
                    not requirement(self.mapping, a)['continuous']
                    for patient in self.patients.values() for plan in patient['candidate_plans']
                    for a in plan['actions'][:-1])
                if simple and self.spaces[rid]['type'] == 'stretcher':
                    merged = []
                    for pid in sorted({h.patient for h in holds}):
                        own = [h for h in holds if h.patient == pid]
                        active = self.cp.NewBoolVar('stretcher_patient')
                        self.cp.AddMaxEquality(active, [h.present for h in own])
                        starts, ends = [], []
                        for h in own:
                            start = self.cp.NewIntVar(0, 120, 'stretcher_start')
                            end = self.cp.NewIntVar(0, 120, 'stretcher_end')
                            self.cp.Add(start == h.start).OnlyEnforceIf(h.present)
                            self.cp.Add(start == 120).OnlyEnforceIf(h.present.Not())
                            self.cp.Add(end == h.end).OnlyEnforceIf(h.present)
                            self.cp.Add(end == 0).OnlyEnforceIf(h.present.Not())
                            starts.append(start)
                            ends.append(end)
                        lo, hi = self.cp.NewIntVar(0, 120, 'stretcher_lo'), self.cp.NewIntVar(0, 120, 'stretcher_hi')
                        size = self.cp.NewIntVar(0, 120, 'stretcher_size')
                        self.cp.AddMinEquality(lo, starts)
                        self.cp.AddMaxEquality(hi, ends)
                        merged.append(self.cp.NewOptionalIntervalVar(lo, size, hi, active, 'stretcher_union'))
                    self.cp.AddNoOverlap(merged)
                elif simple:
                    self.cp.AddNoOverlap([h.interval for h in holds])
                else:
                    for a, b in combinations(holds, 2):
                        if a.patient != b.patient:
                            self._separate(a, b)
            elif rid in self.people:
                if self.r.get('initial_reservations'):
                    for a, b in combinations(holds, 2):
                        if a.task == b.task or (a.patient == b.patient and 'crew' in (a.kind, b.kind) and a.kind != b.kind):
                            continue
                        self._separate(a, b)
                    continue
                ordinary = [h for h in holds if h.kind != 'crew']
                crew = [h for h in holds if h.kind == 'crew']
                self.cp.AddNoOverlap([h.interval for h in ordinary])
                self.cp.AddNoOverlap([h.interval for h in crew])
                for a in crew:
                    for b in ordinary:
                        if a.patient != b.patient:
                            self._separate(a, b)
            else:
                # Duplicate holds of a service capability for alternative spaces of one task
                # are mutually exclusive, so a single NoOverlap is exact here.
                if self.r.get('initial_reservations'):
                    for a, b in combinations(holds, 2):
                        if a.task != b.task and not (a.patient == b.patient and 'crew' in (a.kind, b.kind) and a.kind != b.kind):
                            self._separate(a, b)
                else:
                    self.cp.AddNoOverlap([h.interval for h in holds])
        for holds in patient_spaces.values():
            for a, b in combinations(holds, 2):
                if a.resource != b.resource:
                    self._separate(a, b)

    def _inventory(self):
        for (loc, item), terms in self.spending.items():
            entry = self.r['inventory'].get(loc, {}).get(item)
            if entry is None or entry['quantity'] is None:
                continue  # Validator treats undefined inventory as unchecked, not conflict.
            available = Fraction(str(entry['quantity'])) - Fraction(str(entry.get('reserved', 0)))
            scale = math.lcm(available.denominator, *(coefficient.denominator for coefficient, _ in terms))
            self.cp.Add(sum(int(coefficient * scale) * variable for coefficient, variable in terms) <= int(available * scale))

    def fix_other_patients(self, values, target):
        for pid, decisions in values.items():
            if pid != target:
                for name, variable in self.decisions[pid].items():
                    self.cp.Add(variable == decisions.get(name, 0))
        self.cp.Add(self.selected[target] == 1)

    def values(self, solver):
        return {pid: {key: solver.Value(v) for key, v in values.items()} for pid, values in self.decisions.items()}
