"""Immutable reaction-table reads, window truncation and specified interpolation."""
from bisect import bisect_left
import csv
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path


class TableUnavailable(ValueError):
    pass


def group_id(spec):
    injury = spec['injury']
    kind = injury['injury_type']
    if kind in ('carbon_monoxide_exposure', 'environmental_hypoxia'):
        gas, prefix = ('CarbonMonoxide', 'co') if kind == 'carbon_monoxide_exposure' else ('Oxygen', 'o2')
        return f"{kind}__{prefix}{float(injury['environment_gases'][gas]):g}"
    location = injury.get('compartment') or injury.get('side')
    return f"{kind}{'_' + location if location else ''}__s{float(injury['severity'])}"


def plan_key(plan):
    return '+'.join(a['action_type'] for a in plan['actions'])


@dataclass(frozen=True)
class Cost:
    death: int
    deficit_L: float
    terminal_min: float | None
    interpolated: bool
    measured_delays: tuple

    @property
    def deficit10(self):
        return round(10 * self.deficit_L)


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Nonfinite table value')
    return number


class ReactionTable:
    def __init__(self, name, summary, cumulative):
        self.name = name
        self.rows, self.series, self.missing = {}, {}, []
        for row in csv.DictReader(io.StringIO(cumulative)):
            d = row['d'] if row['d'] == 'untreated' else int(row['d'])
            if d in self.series:
                raise TableUnavailable(f'{name}: duplicate cumulative row {d}')
            self.series[d] = row
        for row in csv.DictReader(io.StringIO(summary)):
            d = row['d'] if row['d'] == 'untreated' else int(row['d'])
            if d in self.rows:
                raise TableUnavailable(f'{name}: duplicate summary row {d}')
            if row['source'] == 'error' or row['window_status'] not in ('complete', 'complete_terminal'):
                self.missing.append(d)
                continue
            self.rows[d] = row

    def _point(self, d, window):
        row = self.rows.get(d)
        value = self.series.get(d, {}).get(f'm{window}')
        if row is None or value in (None, ''):
            return None
        terminal = None if row['terminal_min'] in (None, '') else _number(row['terminal_min'])
        death = int(terminal is not None and terminal <= window)
        return Cost(death, _number(value), terminal if death else None, False, (d,))

    def cost(self, delay, window):
        if type(window) is not int or not 0 <= window <= 120:
            raise ValueError('Window must be an integer in [0, 120]')
        if delay != 'untreated' and (type(delay) is not int or not 0 <= delay <= 120):
            raise ValueError('Delay must be untreated or an integer in [0, 120]')
        exact = self._point(delay, window)
        if exact is not None:
            return exact
        if delay == 'untreated':
            raise TableUnavailable(f'{self.name}: missing untreated at m{window}')
        points = {d: self._point(d, window) for d in self.rows if d != 'untreated'}
        measured = sorted(d for d, point in points.items() if point is not None)
        index = bisect_left(measured, delay)
        if index == 0 or index == len(measured):
            raise TableUnavailable(f'{self.name}: no measured bracket for d={delay}, m{window}; no extrapolation')
        lo, hi = measured[index - 1:index + 1]
        a, b = points[lo], points[hi]
        deficit = a.deficit_L + (b.deficit_L - a.deficit_L) * (delay - lo) / (hi - lo)
        # User clarification: terminal time uses the same upper point as death.
        return Cost(b.death, deficit, b.terminal_min, True, (lo, hi))

    def arrays(self, arrival):
        if int(arrival) != arrival or not 0 <= arrival <= 120:
            raise ValueError('V1 requires integer arrival times in [0, 120]')
        window = 120 - int(arrival)
        values = [self.cost(d, window) for d in range(window + 1)]
        return [v.death for v in values], [v.deficit10 for v in values]

    def non_monotonic(self, window):
        points = [(d, self._point(d, window)) for d in sorted(x for x in self.rows if x != 'untreated')]
        points = [(d, p) for d, p in points if p is not None]
        return [{'table': self.name, 'window_min': window, 'from_d': a, 'to_d': b,
                 'kind': 'death_to_survival'} for (a, x), (b, y) in zip(points, points[1:]) if x.death > y.death]


class TableStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.files = {p.name: p.read_bytes() for p in sorted(self.directory.iterdir()) if p.is_file()}
        self.hashes = {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()}
        self.cache = {}

    def table(self, spec, plan):
        name = f'{group_id(spec)}__{plan_key(plan)}'
        if name not in self.cache:
            filenames = (name + '.csv', name + '__cum_deficit_L.csv')
            if any(f not in self.files for f in filenames):
                raise TableUnavailable(f'没有对应反应表: {name}')
            self.cache[name] = ReactionTable(name, *(self.files[f].decode('utf-8') for f in filenames))
        return self.cache[name]

    def save_snapshot(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        for name, data in self.files.items():
            (directory / name).write_bytes(data)


def prepare_costs(context, specs, store):
    costs, untreated, warnings = {}, {}, []
    for patient in context['patients']:
        pid, arrival = patient['patient_id'], patient['arrival_time_min']
        for plan in patient['candidate_plans']:
            table = store.table(specs[pid], plan)
            costs[pid, plan['plan_id']] = table.arrays(arrival)
            value = table.cost('untreated', 120 - int(arrival))
            if pid in untreated and untreated[pid] != value:
                raise TableUnavailable(f'{pid}: inconsistent untreated rows across plans')
            untreated[pid] = value
            # Report table-level recovery even when it lies beyond this late
            # casualty's shorter observation window, as well as window changes.
            for window in sorted({120, 120 - int(arrival)}):
                warnings.extend(table.non_monotonic(window))
    return costs, untreated, list({str(w): w for w in warnings}.values())
