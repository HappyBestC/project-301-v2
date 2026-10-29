"""Read-only comparison of LLM schedules and native standard-answer executions."""
import argparse
import csv
import glob
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

from core301.agent_chain.audit import RESULTS_ROOT
from core301.paths import PROJECT_ROOT
from .deficit import cumulative_deficit, minute_values
from .scenario import load_scenario

UNTREATED_RUN = Path('/home/private/project-301-v2/experiments/results/agent_chain/agent_chain_run_002_live_003')
REFERENCE = PROJECT_ROOT / 'runs/curve_probe_001/runs/reference_healthy'
BASELINE = PROJECT_ROOT / 'runs/standard_answer/live003_baseline.json'


def read(path):
    return json.loads(Path(path).read_text())


def csv_rows(path):
    with Path(path).open(newline='') as handle:
        return list(csv.DictReader(handle))


def measure(directory, patients, reference):
    result = {}
    for patient in patients:
        pid, arrival = patient['patient_id'], patient['arrival_time_min']
        folder = Path(directory) / 'execution' / pid
        record = read(folder / 'execution.json')
        terminal = record.get('terminal_event')
        if record['arrival_time_min'] != arrival:
            raise ValueError(f'{folder}: arrival time mismatch')
        if (record.get('injury_unsupported') or record.get('treatment_incomplete') or
                (not terminal and (record.get('engine_failure') or not record.get('reached_horizon')))):
            raise ValueError(f'{folder}: incomplete Pulse execution; cannot report complete outcomes')
        terminal_global = terminal['time_min'] if terminal else None
        terminal_relative = terminal_global - arrival if terminal else None
        samples = [{**r, 'time_min': float(r['time_min']) - arrival} for r in csv_rows(folder / 'samples.csv')]
        series = cumulative_deficit(reference, minute_values(samples, 'CardiacOutput_L_min', terminal_relative, True))
        value = series[120 - int(arrival)]
        if value is None or not math.isfinite(value):
            raise ValueError(f'{folder}: incomplete CO samples')
        result[pid] = dict(death=int(terminal is not None and terminal_global <= 120),
                           co_deficit_L=value, terminal_global_min=terminal_global)
    return result


def check_baseline(measured, baseline, reference_path):
    expected = read(baseline)
    if expected['reference_sha256'] != hashlib.sha256(Path(reference_path).read_bytes()).hexdigest():
        raise ValueError('live003 baseline healthy reference hash mismatch')
    rows = {r['patient_id']: r for r in expected['patients']}
    if set(rows) != set(measured):
        raise ValueError('live003 baseline patient mismatch')
    for pid, value in measured.items():
        old = rows[pid]
        if value['death'] != old['death'] or not math.isclose(value['co_deficit_L'], old['deficit_L'], rel_tol=1e-10, abs_tol=1e-8):
            raise ValueError(f'live003 baseline mismatch: {pid}')
    if (sum(v['death'] for v in measured.values()) != expected['deaths'] or not math.isclose(
            sum(v['co_deficit_L'] for v in measured.values()), expected['deficit_L'], rel_tol=1e-10, abs_tol=1e-8)):
        raise ValueError('live003 baseline aggregate mismatch')


def model_metrics(directory, attempts):
    usage, elapsed = [], []
    for attempt in attempts:
        meta = attempt.get('metadata', {})
        audit = Path(directory) / 'schedule' / f"attempt_{attempt['attempt']:02}" / 'llm_request_metadata.json'
        if audit.exists():
            meta = {**meta, **read(audit)}
        usage.append(meta.get('usage'))
        elapsed.append(meta.get('model_elapsed_s'))
    def total(key):
        return sum(u[key] for u in usage) if usage and all(u is not None and key in u for u in usage) else None
    return dict(prompt_tokens=total('prompt_tokens'), completion_tokens=total('completion_tokens'),
                total_tokens=total('total_tokens'),
                model_elapsed_s=sum(elapsed) if elapsed and all(v is not None for v in elapsed) else None)


def run_rows(directory, group, patients, reference, untreated, *, standard=False):
    directory = Path(directory)
    if standard:
        schedule = read(directory / 'schedule.json')
        accepted, attempts = None, []
        measured = measure(directory / 'pulse', patients, reference)
    else:
        state = read(directory / 'state/validate.json')
        schedule, attempts = state['accepted_schedule'], state['schedule_attempts']
        accepted = next((a['attempt'] for a in attempts if a['candidate'] == schedule and
                         not a['validation']['conflicts']), None) if schedule is not None else None
        measured = measure(directory, patients, reference) if schedule is not None else untreated
    selected = schedule['selections'] if schedule is not None else {}
    row = dict(run_id=directory.name, group=group, accepted_attempt=accepted,
               schedule_passed=schedule is not None, scheduled_patients=len(selected),
               conflicts_per_attempt=json.dumps([len(a['validation']['conflicts']) for a in attempts]),
               pulse_deaths=sum(v['death'] for v in measured.values()),
               co_deficit_L=sum(v['co_deficit_L'] for v in measured.values()),
               **model_metrics(directory, attempts))
    details = []
    for patient in patients:
        pid = patient['patient_id']
        delay = None
        if pid in selected:
            plan = next(p for p in patient['candidate_plans'] if p['plan_id'] == selected[pid])
            first = plan['actions'][0]['action_id']
            operation = next(o for o in schedule['operations'] if o['patient_id'] == pid and o['action_id'] == first and o['mode'] == 'start')
            delay = operation['end_min'] - patient['arrival_time_min']
        details.append(dict(run_id=directory.name, group=group, patient_id=pid, scheduled=pid in selected,
                            effective_after_injury_min=delay, **measured[pid]))
    return row, details


def write_csv(path, rows):
    with Path(path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compare_runs(runs, standards, out, *, untreated_run=UNTREATED_RUN, reference_dir=REFERENCE, baseline=BASELINE):
    context, *_ = load_scenario()
    patients = context['patients']
    reference_path = Path(reference_dir) / 'samples.csv'
    reference = minute_values(csv_rows(reference_path), 'CardiacOutput_L_min', None, False)
    if None in reference:
        raise ValueError('Healthy reference is incomplete')
    untreated = measure(untreated_run, patients, reference)
    check_baseline(untreated, baseline, reference_path)
    rows, details = [], []
    for directory in runs:
        manifest = read(Path(directory) / 'manifest.json')
        if manifest.get('mode') != 'live_schedule' or manifest.get('scenario') != 'run_002':
            raise ValueError(f'{directory}: expected live_schedule run_002')
        group = manifest['parameters']['schedule_variant']
        if group not in ('L0', 'L1'):
            raise ValueError('Expected L0 or L1')
        row, personal = run_rows(directory, group, patients, reference, untreated)
        rows.append(row)
        details.extend(personal)
    controls = []
    for directory in standards:
        # Directory names retain G0/G60 labels without guessing solver parameters.
        row, personal = run_rows(directory, Path(directory).name, patients, reference, untreated, standard=True)
        controls.append(row)
        details.extend(personal)
    controls.insert(0, dict(run_id=Path(untreated_run).name, group='untreated', accepted_attempt=None,
        schedule_passed=False, scheduled_patients=0, conflicts_per_attempt='[]',
        pulse_deaths=sum(v['death'] for v in untreated.values()),
        co_deficit_L=sum(v['co_deficit_L'] for v in untreated.values()),
        prompt_tokens=None, completion_tokens=None, total_tokens=None, model_elapsed_s=None))
    details.extend(dict(run_id=Path(untreated_run).name, group='untreated', patient_id=pid,
        scheduled=False, effective_after_injury_min=None, **value) for pid, value in untreated.items())
    summary = ['# LLM baseline V1 comparison', '',
               'Shared CO deficit; individual injury windows H_i; live003 baseline verified. No-accepted-schedule runs count as untreated.', '',
               '| Group | Runs | Schedule pass rate | Deaths mean / min / max | CO deficit L mean / min / max |',
               '|---|---:|---:|---:|---:|']
    for group in ('L0', 'L1'):
        values = [r for r in rows if r['group'] == group]
        if not values:
            continue
        stats = lambda key: ' / '.join(f'{v:.2f}' for v in (mean(r[key] for r in values), min(r[key] for r in values), max(r[key] for r in values)))
        summary.append(f"| {group} | {len(values)} | {sum(r['schedule_passed'] for r in values) / len(values):.2%} | {stats('pulse_deaths')} | {stats('co_deficit_L')} |")
    summary += ['', '| Control | Deaths | CO deficit L |', '|---|---:|---:|']
    summary += [f"| {r['group']} | {r['pulse_deaths']} | {r['co_deficit_L']:.2f} |" for r in controls]
    summary += ['', 'Blank model metrics mean unavailable, not zero. Source runs are read-only.',
                f'Untreated source: `{untreated_run}`', f'Healthy reference: `{reference_dir}`',
                f'Baseline cross-check: `{baseline}`', '']
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'comparison.csv', rows + controls)
    names = [r['run_id'] for r in rows + controls]
    if len(set(names)) != len(names):
        raise ValueError('Run directory names must be unique for per-patient comparison')
    indexed = {(r['patient_id'], r['run_id']): r for r in details}
    wide = []
    for patient in patients:
        pid = patient['patient_id']
        row = {'patient_id': pid}
        for name in names:
            for key in ('scheduled', 'effective_after_injury_min', 'death', 'co_deficit_L'):
                row[f'{name}.{key}'] = indexed[pid, name][key]
        wide.append(row)
    write_csv(out / 'per_patient.csv', wide)
    (out / 'summary.md').write_text('\n'.join(summary))
    return rows, controls, details


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--standard', nargs='+', type=Path, required=True)
    parser.add_argument('--untreated-run', type=Path, default=UNTREATED_RUN)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    runs = []
    for pattern in args.runs:
        path = Path(pattern)
        matches = sorted(glob.glob(str(path if path.is_absolute() or path.parent != Path('.') else RESULTS_ROOT / path)))
        if not matches:
            parser.error(f'No runs matched: {pattern}')
        runs.extend(Path(p) for p in matches)
    compare_runs(list(dict.fromkeys(runs)), args.standard, args.out, untreated_run=args.untreated_run)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
