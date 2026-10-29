"""Shared reaction-table CO deficit calculation (unchanged probe arithmetic)."""

HORIZON_MIN = 120


def minute_values(samples, column, terminal_min, zero_after_terminal):
    points = {}
    for row in samples:
        if row.get(column) not in (None, ''):
            points[float(row['time_min'])] = float(row[column])
    times = sorted(points)
    values = []
    for minute in range(HORIZON_MIN + 1):
        if terminal_min is not None and minute >= terminal_min:
            values.append(0.0 if zero_after_terminal else None)
            continue
        if not times or minute < times[0] - 1e-9 or minute > times[-1] + 1e-9:
            values.append(None)
            continue
        hi = next(i for i, t in enumerate(times) if t >= minute - 1e-9)
        if abs(times[hi] - minute) < 1e-9 or hi == 0:
            values.append(points[times[hi]])
        else:
            t0, t1 = times[hi - 1], times[hi]
            v0, v1 = points[t0], points[t1]
            values.append(v0 + (v1 - v0) * (minute - t0) / (t1 - t0))
    return values


def cumulative_deficit(reference, values):
    series, total = [0.0], 0.0
    for minute in range(1, HORIZON_MIN + 1):
        a, b, ra, rb = values[minute - 1], values[minute], reference[minute - 1], reference[minute]
        if None in (a, b, ra, rb) or total is None:
            total = None
        else:
            total += 0.5 * (max(0.0, ra - a) + max(0.0, rb - b))
        series.append(total)
    return series

