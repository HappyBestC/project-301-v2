#!/usr/bin/env python3
"""Pulse reaction tables for the run_002 injury types. Pulse only, no model calls.

For every (injury type, severity/level, treatment plan) this measures what happens
when the plan's first action takes effect d minutes after injury, d = 0..120,
plus one untreated run per (injury type, severity/level) and one healthy
reference run. Every run goes through core301.agent_chain.bridge.execute_patient,
the same Pulse path the agent chain uses, so tables and later re-checks agree.

Server usage:
    source scripts/activate.sh
    python scripts/curve_probe.py plan                                   # counts only
    python scripts/curve_probe.py run --phase smoke --out runs/curve_probe_001
    python scripts/curve_probe.py run --phase full  --out runs/curve_probe_001
    python scripts/curve_probe.py summarize --out runs/curve_probe_001

Definitions
- d: minutes from injury to the END of the plan's first operation (effect time).
- Follow-up actions start the moment the previous one ends, so their effect time
  is d + the sum of their durations (config/medical_resources_v1_1/actions.json).
  Actions whose effect time falls after minute 120 are dropped and recorded.
- Terminal event: first active IrreversibleState or CardiacArrest (bridge rule).
- If the untreated run ends at minute T and d >= T, the first action could never
  be applied, so that row is copied from the untreated run instead of simulated.

`run` is resumable: finished runs (result.json present) are skipped.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from core301.standard_answer.deficit import minute_values, cumulative_deficit

SCENARIO_DIR = ROOT / 'dataset_v1' / 'run_002'
ACTIONS_JSON = ROOT / 'config' / 'medical_resources_v1_1' / 'actions.json'
HORIZON_MIN = 120
DELAYS = tuple(range(0, HORIZON_MIN + 1))
SEVERITIES = (0.2, 0.4, 0.6, 0.8, 1.0)
# Environmental exposures have no 0-1 severity; levels are ambient volume fractions.
# run_002 uses CO 0.005 and O2 0.12. The other levels are assumptions to confirm.
CO_LEVELS = (0.001, 0.0025, 0.005, 0.0075, 0.01)
O2_LEVELS = (0.16, 0.14, 0.12, 0.10, 0.08)
ENVIRONMENTAL = ('carbon_monoxide_exposure', 'environmental_hypoxia')
PROBE_PID = 'P01'
SMOKE_DELAY = 10
# gapcheck: follow-ups delayed by extra minutes after the first action (e.g. bleeding
# controlled in the ambulance, fluids only after arrival at an aid station).
GAPCHECK_DELAYS = (10,)
GAPS = (0, 10, 20, 30, 45, 60)
# coarse: every 5 minutes (a subset of the 1-minute grid, so `full` later only fills in).
COARSE_DELAYS = tuple(range(0, HORIZON_MIN + 1, 5))
# refine: fill 1-minute points where death flips or the 120-min deficit jumps by more than this.
REFINE_DEFICIT_L = 25.0
# live_003: untreated external hemorrhage RightLeg 0.4 ended 73 min after injury
# (P01 at 73, P09 at 83 injured at 10, P15 at 93 injured at 20).
PARITY_EXPECTED_MIN = 73.0
PARITY_GROUP = 'external_hemorrhage_RightLeg__s0.4'


# --------------------------------------------------------------------------- plan

def _location(injury):
    return injury.get('compartment') or injury.get('side') or ''


def load_plans():
    from core301.dispatch.minimal.api import requirement
    templates = json.loads((SCENARIO_DIR / 'action_plan_templates.json').read_text())
    mapping = json.loads(ACTIONS_JSON.read_text())
    # Scheduled duration exactly as the validator computes it, with a new IV access
    # (transfusion = 3 min separate access phase + 8 min; fluid = 5 min).
    durations = {k: requirement(mapping, {'action_type': k, 'depends_on': [], 'target': {}},
                                access_mode='new')['duration_min'] for k in mapping['actions']}
    plans = {}
    for template in templates:
        sequence = tuple(a['action_type'] for a in template['actions'])
        bucket = plans.setdefault(template['injury_type'], [])
        if any(p['sequence'] == list(sequence) for p in bucket):
            continue
        steps, offset = [], 0
        for i, action in enumerate(template['actions']):
            if i:
                if action['depends_on'] != [template['actions'][i - 1]['action_id']]:
                    raise SystemExit('Non-linear plan, not supported: ' + template['plan_id'])
                offset += durations[action['action_type']]
            # Same target projection as dispatch.minimal.api.load_cases: only the
            # mapping's target_kind (side/compartment) is kept; 'patient' keeps none.
            kind = mapping['actions'][action['action_type']]['target_kind']
            target = {kind: action['target'][kind]} if kind in ('side', 'compartment') else {}
            steps.append({'action_type': action['action_type'], 'offset_min': offset, 'target': target})
        bucket.append({'plan_key': '+'.join(sequence), 'sequence': list(sequence), 'steps': steps,
                       'source_plan_id': template['plan_id'],
                       # Offsets are part of the directory name, so a changed template never reuses old runs.
                       'dir': '+'.join(sequence) + '@' + ','.join(str(s['offset_min']) for s in steps)})
    return plans


def with_gap(plan, gap):
    """The same plan with every follow-up action delayed by `gap` extra minutes."""
    steps = [dict(s, offset_min=s['offset_min'] + (gap if i else 0)) for i, s in enumerate(plan['steps'])]
    return dict(plan, steps=steps)


def load_groups():
    from core301.pulse.v2.protocol_book import OPEN_INJURIES
    specs = json.loads((SCENARIO_DIR / 'patient_specs.json').read_text())
    plans = load_plans()
    groups, seen = [], set()
    for spec in specs:
        injury = spec['injury']
        kind = injury['injury_type']
        if kind in seen:
            continue
        seen.add(kind)
        if kind in ENVIRONMENTAL:
            base = injury['environment_gases']
            levels = CO_LEVELS if kind == 'carbon_monoxide_exposure' else O2_LEVELS
            for level in levels:
                gases = dict(base)
                if kind == 'carbon_monoxide_exposure':
                    gases['CarbonMonoxide'] = level
                else:
                    gases['Oxygen'], gases['CarbonMonoxide'] = level, 0.0
                gases['Nitrogen'] = 1 - gases['Oxygen'] - 0.0004 - gases['CarbonMonoxide']
                label = 'co' if kind == 'carbon_monoxide_exposure' else 'o2'
                scenario_level = abs(level - (base['CarbonMonoxide'] if label == 'co' else base['Oxygen'])) < 1e-12
                groups.append({'group_id': f'{kind}__{label}{level:g}', 'injury_type': kind, 'location': '',
                               'level': level, 'injury': {'injury_type': kind, 'environment_gases': gases},
                               'plans': plans[kind], 'verified_scope': scenario_level,
                               'scenario_level': scenario_level, 'dehydration_override': False})
            continue
        for severity in SEVERITIES:
            variant = {**injury, 'severity': severity}
            location = _location(injury)
            open_levels = OPEN_INJURIES.get(kind, ((), None, None))[0]
            groups.append({'group_id': f'{kind}{"_" + location if location else ""}__s{severity:.1f}',
                           'injury_type': kind, 'location': location, 'level': severity, 'injury': variant,
                           'plans': plans[kind], 'verified_scope': severity in open_levels,
                           'scenario_level': abs(severity - injury['severity']) < 1e-12,
                           'dehydration_override': kind == 'dehydration' and severity not in (0.2, 0.4, 0.6)})
    # run_002's own severities/levels first, so the scenario's standard answer is available early.
    return sorted(groups, key=lambda g: not g['scenario_level'])


REFERENCE = {'group_id': 'reference_healthy', 'injury_type': 'reference', 'location': 'RightLeg', 'level': 0.0,
             'injury': {'injury_type': 'external_hemorrhage', 'severity': 0.0, 'compartment': 'RightLeg'},
             'plans': [], 'verified_scope': True, 'scenario_level': True, 'dehydration_override': False}


def task(kind, group, plan=None, d=None, rel=None):
    if rel is None:
        rel = (f'runs/{group["group_id"]}/untreated' if kind != 'treated'
               else f'runs/{group["group_id"]}/{plan["dir"]}/d{d:03d}')
    return {'kind': kind, 'group': group, 'plan': plan, 'd': d, 'rel_dir': rel}


# --------------------------------------------------------------------------- worker

def _patch_dehydration(bridge):
    """Same PatientConfiguration as PatientInitializer, without its 0.2/0.4/0.6 gate."""
    from core301.paths import PULSE_ROOT
    from core301.pulse.injury_adapter import scalar

    class ProbeInitializer:
        def configuration(self, casualty):
            severity = casualty['injuries'][0]['severity']
            return {'DataRoot': str(PULSE_ROOT), 'PatientFile': str(PULSE_ROOT / 'patients/StandardMale.json'),
                    'Conditions': {'AnyCondition': [{'PatientCondition': {'Dehydration': {
                        'Severity': scalar('0To1', severity)}}}]}}
    bridge.PatientInitializer = ProbeInitializer


def _write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def run_task(item, out_root, native, keep_logs):
    directory = Path(out_root) / item['rel_dir']
    group, plan = item['group'], item['plan']
    base = {'kind': item['kind'], 'group_id': group['group_id'], 'plan_key': plan['plan_key'] if plan else None,
            'd': item['d'], 'rel_dir': item['rel_dir']}
    try:
        from core301.agent_chain import bridge
        from core301.agent_chain.outcomes import patient_outcome
        if group['dehydration_override']:
            _patch_dehydration(bridge)
        if directory.exists():
            shutil.rmtree(directory)  # leftovers of an interrupted attempt
        spec = {'patient_id': PROBE_PID, 'arrival_time_min': 0, 'injury': group['injury'],
                'location_id': 'probe', 'base_patient': 'StandardMale'}
        timeline = [{'event': 'injury_onset', 'patient_id': PROBE_PID, 'time_min': 0, 'location': 'probe',
                     'treatment_status': 'scheduled'}]
        dropped = []
        if item['kind'] == 'treated':
            for i, step in enumerate(plan['steps'], 1):
                when = item['d'] + step['offset_min']
                event = {'event': 'apply_action', 'patient_id': PROBE_PID, 'task_id': f'probe-t{i}',
                         'action_id': f'probe-a{i}', 'action_type': step['action_type'],
                         'target': {'patient_id': PROBE_PID, **step['target']}, 'location': 'probe',
                         'time_min': when}
                (timeline if when <= HORIZON_MIN else dropped).append(event)
        record = bridge.execute_patient(spec, timeline, directory, horizon_min=HORIZON_MIN, native=native)
        outcome = patient_outcome(record, HORIZON_MIN)
        failed = outcome['engine_failure'] or outcome['injury_unsupported'] or outcome['treatment_incomplete']
        log = directory / 'pulse.log'
        if log.exists() and not failed and not keep_logs:
            log.unlink()
        result = {**base, 'source': 'run', 'outcome': outcome, 'dropped_actions': dropped,
                  'action_status': [{k: a.get(k) for k in ('action_type', 'time_min', 'status', 'accepted')}
                                    for a in record['actions']],
                  'wall_elapsed_s': record.get('wall_elapsed_s'), 'speed_ratio': record.get('speed_ratio'),
                  'dehydration_override': group['dehydration_override']}
    except Exception as exc:  # keep going; the failure is recorded and retried on the next run
        directory.mkdir(parents=True, exist_ok=True)
        result = {**base, 'source': 'run', 'worker_error': {'type': type(exc).__name__, 'detail': str(exc),
                                                            'traceback': traceback.format_exc()[-4000:]}}
    _write_json(directory / 'result.json', result)


# --------------------------------------------------------------------------- run

def read_result(out, rel):
    path = Path(out) / rel / 'result.json'
    return json.loads(path.read_text()) if path.exists() else None


def done(out, rel):
    result = read_result(out, rel)
    return result is not None and 'worker_error' not in result


def execute(tasks, out, workers, native, keep_logs, label):
    """One fresh OS process per run: a native crash only loses that run."""
    pending = [t for t in tasks if not done(out, t['rel_dir'])]
    print(f'[{label}] {len(tasks)} tasks, {len(tasks) - len(pending)} already done, {len(pending)} to run '
          f'on {workers} workers', flush=True)
    if not pending:
        return
    queue = Path(out) / 'queue'
    queue.mkdir(exist_ok=True)
    running, remaining = {}, iter(pending)
    start, finished, errors, last, exhausted = time.time(), 0, 0, 0.0, False

    def launch(item):
        path = queue / (item['rel_dir'].replace('/', '__') + '.json')
        _write_json(path, item)
        command = [sys.executable, str(Path(__file__).resolve()), '_one', '--task', str(path), '--out', str(out)]
        command += ([] if native else ['--fake']) + (['--keep-logs'] if keep_logs else [])
        log = path.with_suffix('.log').open('w')
        running[subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)] = (item, path, log)

    while running or not exhausted:
        while not exhausted and len(running) < workers:
            try:
                launch(next(remaining))
            except StopIteration:
                exhausted = True
        time.sleep(0.5)
        for process in [p for p in running if p.poll() is not None]:
            item, path, log = running.pop(process)
            log.close()
            finished += 1
            if done(out, item['rel_dir']):
                path.unlink(missing_ok=True)
                path.with_suffix('.log').unlink(missing_ok=True)
                continue
            errors += 1
            if read_result(out, item['rel_dir']) is None:  # the process died before writing a result
                directory = Path(out) / item['rel_dir']
                directory.mkdir(parents=True, exist_ok=True)
                _write_json(directory / 'result.json', {
                    'kind': item['kind'], 'group_id': item['group']['group_id'],
                    'plan_key': item['plan']['plan_key'] if item['plan'] else None, 'd': item['d'],
                    'rel_dir': item['rel_dir'], 'source': 'run',
                    'worker_error': {'type': 'PROCESS_EXIT', 'detail': f'exit code {process.returncode}',
                                     'traceback': path.with_suffix('.log').read_text()[-4000:]}})
        now = time.time()
        if now - last > 60 or (exhausted and not running):
            last = now
            # Runs start together, so the early rate is meaningless; report ETA after a full batch.
            eta = ((len(pending) - finished) * (now - start) / finished / 60) if finished >= workers else None
            print(f'[{label}] {finished}/{len(pending)} done, {len(running)} running, {errors} errors, '
                  f'elapsed {(now - start) / 60:.1f} min'
                  + (f', ETA {eta:.0f} min' if eta is not None else ''), flush=True)


def cmd_one(args):
    item = json.loads(Path(args.task).read_text())
    run_task(item, args.out, not args.fake, args.keep_logs)


def git_head():
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def treated_tasks(groups, out, delays):
    """`delays` is a tuple, or a function (group, plan) -> delays."""
    tasks, copies = [], []
    for group in groups:
        untreated = read_result(out, task('untreated', group)['rel_dir'])
        outcome = (untreated or {}).get('outcome') or {}
        terminal = outcome.get('terminal_event')
        cutoff = terminal['time_min'] if terminal and not outcome.get('engine_failure') else None
        for plan in group['plans']:
            for d in (delays(group, plan) if callable(delays) else delays):
                item = task('treated', group, plan, d)
                (copies if cutoff is not None and d >= cutoff else tasks).append(item)
    return tasks, copies


def write_copies(copies, out):
    for item in copies:
        if done(out, item['rel_dir']):
            continue
        source = read_result(out, task('untreated', item['group'])['rel_dir'])
        directory = Path(out) / item['rel_dir']
        directory.mkdir(parents=True, exist_ok=True)
        _write_json(directory / 'result.json', {
            'kind': 'treated', 'group_id': item['group']['group_id'], 'plan_key': item['plan']['plan_key'],
            'd': item['d'], 'rel_dir': item['rel_dir'], 'source': 'copied_from_untreated',
            'copied_from': source['rel_dir'], 'outcome': source['outcome'], 'dropped_actions': [],
            'dehydration_override': item['group']['dehydration_override']})


def cmd_plan(args):
    groups = load_groups()
    plans = sum(len(g['plans']) for g in groups)
    print(f'{len(groups)} groups (injury type x severity/level), {plans} plan tables')
    for g in groups:
        flags = ('' if g['verified_scope'] else '  [outside verified scope]') + \
                ('  [dehydration override]' if g['dehydration_override'] else '')
        print(f'  {g["group_id"]}: ' + ', '.join(
            p['plan_key'] + '(' + ','.join(f'+{s["offset_min"]}' for s in p['steps']) + ')' for p in g['plans'])
            + flags)
    print(f'runs before the untreated-cutoff skip: 1 reference + {len(groups)} untreated + '
          f'{plans * len(DELAYS)} treated = {1 + len(groups) + plans * len(DELAYS)}')
    print(f'smoke phase: 1 reference + {len(groups)} untreated + {plans} treated (d={SMOKE_DELAY}) '
          f'+ 2 repeatability checks = {1 + len(groups) + plans + 2}')
    print(f'coarse phase: {plans} tables x {len(COARSE_DELAYS)} delays (every 5 min) = {plans * len(COARSE_DELAYS)} '
          f'treated runs before the untreated-cutoff skip; refine then fills 1-min points near transitions')
    multi = sum(len(p['steps']) > 1 for g in groups for p in g['plans'])
    print(f'gapcheck phase: {multi} multi-step plan tables x {len(GAPCHECK_DELAYS)} delays x {len(GAPS)} gaps '
          f'= {multi * len(GAPCHECK_DELAYS) * len(GAPS)} runs (reuses reference and untreated runs)')


def cmd_run(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    groups = load_groups()
    workers = args.workers or max(1, (os.cpu_count() or 2) - 2)
    native = not args.fake
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    _write_json(out / f'manifest_{args.phase}_{stamp}.json', {
        'phase': args.phase, 'git_head': git_head(), 'native': native, 'workers': workers,
        'horizon_min': HORIZON_MIN, 'delays': [DELAYS[0], DELAYS[-1]], 'severities': SEVERITIES,
        'co_levels': CO_LEVELS, 'o2_levels': O2_LEVELS, 'gapcheck_delays': GAPCHECK_DELAYS, 'gaps': GAPS,
        'groups': groups, 'reference': REFERENCE,
        'definition': __doc__})
    stage1 = [task('reference', REFERENCE, rel='runs/reference_healthy')] + [task('untreated', g) for g in groups]
    if args.phase == 'smoke':
        ext = next(g for g in groups if g['group_id'] == PARITY_GROUP)
        stage1 += [task('untreated', ext, rel='checks/repeat_untreated'),
                   task('treated', ext, ext['plans'][0], SMOKE_DELAY, rel='checks/repeat_treated')]
    execute(stage1, out, workers, native, args.keep_logs, 'stage1 reference+untreated')
    if args.phase == 'gapcheck':
        tasks = [task('treated', g, with_gap(p, gap), d,
                      rel=f'runs/{g["group_id"]}/{p["dir"]}/gap{gap:02d}/d{d:03d}')
                 for g in groups for p in g['plans'] if len(p['steps']) > 1
                 for d in GAPCHECK_DELAYS for gap in GAPS]
        execute(tasks, out, workers, native, args.keep_logs, 'gapcheck')
        gap_report(groups, out)
        return
    delays = {'smoke': (SMOKE_DELAY,), 'coarse': COARSE_DELAYS, 'full': DELAYS}.get(args.phase)
    if args.phase == 'refine':
        delays = refine_delays(out)
    tasks, copies = treated_tasks(groups, out, delays)
    write_copies(copies, out)
    print(f'[stage2] {len(copies)} rows copied from untreated (first action after the untreated end)')
    execute(tasks, out, workers, native, args.keep_logs, 'stage2 treated')
    if args.phase == 'smoke':
        smoke_report(groups, out, workers)
    summarize(out)


def refine_delays(out):
    """1-minute points between adjacent coarse points where death flips or the deficit jumps."""
    ref = read_result(out, 'runs/reference_healthy')
    if not ref or 'worker_error' in ref:
        raise SystemExit('refine needs the reference run; run --phase coarse first')
    reference = minute_values(_samples(out, 'runs/reference_healthy'), 'CardiacOutput_L_min', None, False)

    def pick(group, plan):
        rows = {}
        for d in COARSE_DELAYS:
            row, _ = row_for(out, group, plan['plan_key'], d, task('treated', group, plan, d)['rel_dir'], reference)
            if row.get('window_status') in ('complete', 'complete_terminal'):
                rows[d] = row
        extra = []
        for a, b in zip(COARSE_DELAYS, COARSE_DELAYS[1:]):
            if a not in rows or b not in rows:
                continue
            flip = (rows[a]['terminal_min'] is None) != (rows[b]['terminal_min'] is None)
            da, db = rows[a]['deficit_L_120'], rows[b]['deficit_L_120']
            jump = da is not None and db is not None and abs(db - da) > REFINE_DEFICIT_L
            if flip or jump:
                extra.extend(range(a + 1, b))
        return tuple(extra)
    return pick


def _samples(out, rel):
    with (Path(out) / rel / 'samples.csv').open() as handle:
        return list(csv.DictReader(handle))


def smoke_report(groups, out, workers):
    report = {'errors': [], 'not_complete': []}
    for path in sorted(Path(out).glob('**/result.json')):
        result = json.loads(path.read_text())
        if 'worker_error' in result:
            report['errors'].append({'rel_dir': result['rel_dir'], **result['worker_error']})
            continue
        outcome = result['outcome']
        if outcome['window_status'] not in ('complete', 'complete_terminal') or outcome['treatment_incomplete']:
            report['not_complete'].append({'rel_dir': result['rel_dir'], 'window_status': outcome['window_status'],
                                           'treatment_incomplete': outcome['treatment_incomplete'],
                                           'reasons': [outcome.get('injury_unsupported_reason'),
                                                       outcome.get('engine_failure_reason'),
                                                       outcome.get('unsupported_action_reasons')]})
    ext = next(g for g in groups if g['group_id'] == PARITY_GROUP)
    pairs = {'untreated': (f'runs/{PARITY_GROUP}/untreated', 'checks/repeat_untreated'),
             'treated': (f'runs/{PARITY_GROUP}/{ext["plans"][0]["dir"]}/d{SMOKE_DELAY:03d}',
                         'checks/repeat_treated')}
    report['repeatability'] = {}
    for name, (a, b) in pairs.items():
        try:
            report['repeatability'][name] = _samples(out, a) == _samples(out, b)
        except FileNotFoundError:
            report['repeatability'][name] = None
    parity = read_result(out, f'runs/{PARITY_GROUP}/untreated')
    terminal = (parity or {}).get('outcome', {}).get('terminal_event')
    report['parity_live_003'] = {'expected_terminal_min': PARITY_EXPECTED_MIN,
                                 'observed_terminal_min': terminal['time_min'] if terminal else None,
                                 'match_within_1_min': bool(terminal) and abs(terminal['time_min']
                                                                              - PARITY_EXPECTED_MIN) <= 1.0}
    walls = [json.loads(p.read_text()).get('wall_elapsed_s') for p in Path(out).glob('runs/*/*/d*/result.json')]
    walls = [w for w in walls if w]
    full_tasks, full_copies = treated_tasks(groups, out, DELAYS)
    remaining = [t for t in full_tasks if not done(out, t['rel_dir'])]
    if walls:
        per_run = max(walls)  # d=10 runs simulate almost the whole window: an upper bound per run
        mean = sum(walls) / len(walls)
        report['full_estimate'] = {'treated_runs_to_simulate': len(remaining), 'rows_copied': len(full_copies),
                                   'mean_wall_s_per_run': mean, 'upper_bound_wall_s_per_run': per_run,
                                   'workers': workers, 'mean_hours': len(remaining) * mean / workers / 3600,
                                   'upper_bound_hours': len(remaining) * per_run / workers / 3600}
    _write_json(Path(out) / 'smoke_report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'errors'} | {'errors': len(report['errors'])},
                     ensure_ascii=False, indent=1))


# --------------------------------------------------------------------------- summarize



FIELDS = ('group_id', 'injury_type', 'location', 'level', 'plan_key', 'd', 'source', 'window_status',
          'terminal_event', 'terminal_min', 'first_hypovolemic_shock_min', 'integral_CO_L', 'deficit_L_120',
          'min_SpO2', 'minutes_SpO2_below_0_90', 'verified_scope', 'dehydration_override', 'exploratory',
          'treatment_incomplete', 'engine_failure', 'dropped_actions', 'error')


def row_for(out, group, plan_key, d, rel, reference):
    result = read_result(out, rel)
    base = {'group_id': group['group_id'], 'injury_type': group['injury_type'], 'location': group['location'],
            'level': group['level'], 'plan_key': plan_key, 'd': d, 'verified_scope': group['verified_scope'],
            'dehydration_override': group['dehydration_override']}
    if result is None or 'worker_error' in result:
        return {**base, 'source': 'missing' if result is None else 'error',
                'error': (result or {}).get('worker_error', {}).get('type')}, None
    outcome = result['outcome']
    terminal = outcome['terminal_event']
    terminal_min = terminal['time_min'] if terminal else None
    source_rel = result.get('copied_from', rel)
    try:
        samples = _samples(out, source_rel)
    except FileNotFoundError:
        samples = []
    complete = outcome['window_status'] in ('complete', 'complete_terminal')
    series = None
    if reference is not None and complete:
        series = cumulative_deficit(reference, minute_values(samples, 'CardiacOutput_L_min', terminal_min, True))
    spo2 = [float(s['SpO2']) for s in samples if s.get('phase') == 'sample' and s.get('SpO2') not in (None, '')]
    row = {**base, 'source': result['source'], 'window_status': outcome['window_status'],
           'terminal_event': terminal['event'] if terminal else '', 'terminal_min': terminal_min,
           'first_hypovolemic_shock_min': outcome['first_hypovolemic_shock_min'],
           'integral_CO_L': outcome['integral_CO_L'], 'deficit_L_120': series[-1] if series else None,
           'min_SpO2': min(spo2) if spo2 else None,
           'minutes_SpO2_below_0_90': sum(v < 0.90 for v in spo2) if spo2 else None,
           'exploratory': outcome['exploratory'], 'treatment_incomplete': outcome['treatment_incomplete'],
           'engine_failure': outcome['engine_failure'], 'dropped_actions': len(result.get('dropped_actions', [])),
           'error': ''}
    return row, series


def summarize(out):
    out = Path(out)
    groups = load_groups()
    tables = out / 'tables'
    tables.mkdir(exist_ok=True)
    ref_result = read_result(out, 'runs/reference_healthy')
    reference = None
    if ref_result and 'worker_error' not in ref_result and \
            ref_result['outcome']['window_status'] == 'complete':
        reference = minute_values(_samples(out, 'runs/reference_healthy'), 'CardiacOutput_L_min', None, False)
        if None in reference:
            reference = None
    summary = {'reference_ok': reference is not None,
               'reference_integral_CO_L': ref_result['outcome']['integral_CO_L'] if ref_result and
               'outcome' in ref_result else None,
               'rows': 0, 'by_source': {}, 'by_window_status': {}, 'problems': [], 'non_monotonic': []}
    all_rows = []
    for group in groups:
        untreated_row, untreated_series = row_for(out, group, '', 'untreated', task('untreated', group)['rel_dir'],
                                                  reference)
        for plan in group['plans']:
            rows, series_rows = [untreated_row | {'plan_key': plan['plan_key']}], [('untreated', untreated_series)]
            for d in DELAYS:
                row, series = row_for(out, group, plan['plan_key'], d, task('treated', group, plan, d)['rel_dir'],
                                      reference)
                if row['source'] == 'missing':  # not measured (yet) in this phase
                    continue
                rows.append(row)
                series_rows.append((d, series))
            name = f'{group["group_id"]}__{plan["plan_key"]}'
            with (tables / f'{name}.csv').open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            with (tables / f'{name}__cum_deficit_L.csv').open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['d'] + [f'm{m}' for m in range(HORIZON_MIN + 1)])
                for d, series in series_rows:
                    writer.writerow([d] + (series if series else [''] * (HORIZON_MIN + 1)))
            measured = [r for r in rows[1:] if r.get('window_status') in ('complete', 'complete_terminal')]
            for prev, cur in zip(measured, measured[1:]):
                if prev['terminal_min'] is not None and cur['terminal_min'] is None:
                    summary['non_monotonic'].append({'table': name, 'd': cur['d'], 'kind': 'death_to_survival'})
                if None not in (prev['deficit_L_120'], cur['deficit_L_120']) and \
                        cur['deficit_L_120'] < prev['deficit_L_120'] - 1.0:
                    summary['non_monotonic'].append({'table': name, 'd': cur['d'], 'kind': 'deficit_drop_gt_1L',
                                                     'from': prev['deficit_L_120'], 'to': cur['deficit_L_120']})
            all_rows.extend(rows)
    for row in all_rows:
        summary['rows'] += 1
        summary['by_source'][row['source']] = summary['by_source'].get(row['source'], 0) + 1
        status = row.get('window_status', row['source'])
        summary['by_window_status'][status] = summary['by_window_status'].get(status, 0) + 1
        if row['source'] in ('missing', 'error') or row.get('engine_failure') or row.get('treatment_incomplete') \
                or row.get('window_status') not in ('complete', 'complete_terminal'):
            summary['problems'].append({k: row.get(k) for k in ('group_id', 'plan_key', 'd', 'source',
                                                                 'window_status', 'error')})
    with (tables / 'all_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    summary['problem_count'] = len(summary['problems'])
    summary['problems'] = summary['problems'][:200]
    _write_json(out / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('problems', 'non_monotonic')}
                     | {'non_monotonic': len(summary['non_monotonic'])}, ensure_ascii=False, indent=1))


def gap_report(groups, out):
    """How much do outcomes change when follow-up actions are delayed (transport gaps)?"""
    ref_rel = 'runs/reference_healthy'
    ref_result = read_result(out, ref_rel)
    reference = None
    if ref_result and 'worker_error' not in ref_result and ref_result['outcome']['window_status'] == 'complete':
        reference = minute_values(_samples(out, ref_rel), 'CardiacOutput_L_min', None, False)
    rows, findings = [], []
    for g in groups:
        for p in g['plans']:
            if len(p['steps']) < 2:
                continue
            for d in GAPCHECK_DELAYS:
                cells = []
                for gap in GAPS:
                    row, _ = row_for(out, g, p['plan_key'], d, f'runs/{g["group_id"]}/{p["dir"]}/gap{gap:02d}/d{d:03d}',
                                     reference)
                    row['gap'] = gap
                    rows.append(row)
                    cells.append(row)
                ok = [c for c in cells if c.get('window_status') in ('complete', 'complete_terminal')]
                deficits = [c['deficit_L_120'] for c in ok if c.get('deficit_L_120') is not None]
                deaths = {c['gap']: c['terminal_min'] is not None for c in ok}
                findings.append({'group_id': g['group_id'], 'plan_key': p['plan_key'], 'd': d,
                                 'measured_gaps': [c['gap'] for c in ok],
                                 'death_by_gap': deaths, 'death_changes_with_gap': len(set(deaths.values())) > 1,
                                 'deficit_range_L': (max(deficits) - min(deficits)) if deficits else None,
                                 'deficit_by_gap': {c['gap']: c['deficit_L_120'] for c in ok}})
    with (Path(out) / 'gap_check.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=('gap',) + FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    report = {'gaps_min': GAPS, 'delays_min': GAPCHECK_DELAYS,
              'rows_not_clean': [{k: r.get(k) for k in ('group_id', 'plan_key', 'gap', 'source', 'window_status',
                                                        'treatment_incomplete', 'error')}
                                 for r in rows if r.get('treatment_incomplete') or r.get('engine_failure')
                                 or r['source'] in ('missing', 'error')],
              'tables_where_death_changes': sum(f['death_changes_with_gap'] for f in findings),
              'max_deficit_range_L': max((f['deficit_range_L'] for f in findings if f['deficit_range_L'] is not None),
                                         default=None),
              'findings': findings}
    _write_json(Path(out) / 'gap_report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('findings', 'rows_not_clean')}
                     | {'rows_not_clean': len(report['rows_not_clean'])}, ensure_ascii=False, indent=1))
    for f in findings:
        print(f'  {f["group_id"]} {f["plan_key"]} d={f["d"]}: death changes={f["death_changes_with_gap"]}, '
              f'deficit range={f["deficit_range_L"]}')


def cmd_summarize(args):
    summarize(Path(args.out).resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan')
    run = sub.add_parser('run')
    run.add_argument('--phase', choices=('smoke', 'gapcheck', 'coarse', 'refine', 'full'), required=True)
    run.add_argument('--out', required=True)
    run.add_argument('--workers', type=int, default=None, help='default: CPU count - 2')
    run.add_argument('--keep-logs', action='store_true', help='keep pulse.log for successful runs')
    run.add_argument('--fake', action='store_true', help='FakePulse pipeline test, no physiology')
    summ = sub.add_parser('summarize')
    summ.add_argument('--out', required=True)
    one = sub.add_parser('_one', help=argparse.SUPPRESS)
    one.add_argument('--task', required=True)
    one.add_argument('--out', required=True)
    one.add_argument('--fake', action='store_true')
    one.add_argument('--keep-logs', action='store_true')
    args = parser.parse_args()
    {'plan': cmd_plan, 'run': cmd_run, 'summarize': cmd_summarize, '_one': cmd_one}[args.command](args)


if __name__ == '__main__':
    main()
