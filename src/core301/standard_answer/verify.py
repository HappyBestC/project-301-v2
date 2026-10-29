"""Validator and native Pulse comparison, without an LLM dependency."""
import csv
import json
from pathlib import Path

from core301.dispatch.minimal.validation import validate_schedule
from .deficit import minute_values, cumulative_deficit


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def compare(prediction, measured):
    rows = []
    for expected in prediction['patients']:
        actual = measured[expected['patient_id']]
        reasons = []
        if not actual['complete']:
            reasons.append('Pulse 窗口未完成或执行失败')
        death_matches = actual['death'] == expected['death'] if actual['complete'] else False
        if not death_matches:
            reasons.append('死亡与否不同')
        terminal_difference = (abs(actual['terminal_global_min'] - expected['terminal_global_min'])
            if actual['terminal_global_min'] is not None and expected['terminal_global_min'] is not None else None)
        if terminal_difference is not None and terminal_difference > 1 and not expected['interpolated']:
            reasons.append('死亡时刻相差超过 1 分钟')
        deficit_difference = abs(actual['deficit_L'] - expected['deficit_L']) if actual['deficit_L'] is not None else None
        tolerance = max(2.0, abs(expected['deficit_L']) * 0.02)
        if deficit_difference is None or deficit_difference > tolerance:
            reasons.append('CO 缺损超出容差')
        possible_causes = []
        if reasons and expected['interpolated']:
            possible_causes.append('反应表在未测量延迟点插值')
        if reasons and actual['followup_deviations_min']:
            possible_causes.append('后续动作生效时刻偏离反应表模板')
        if reasons and not possible_causes:
            possible_causes.append('需检查 Pulse 执行记录、输入和反应表版本')
        rows.append(dict(patient_id=expected['patient_id'], consistent=not reasons, reasons=reasons,
            interpolated=expected['interpolated'], terminal_difference_min=terminal_difference,
            terminal_difference_report_only=expected['interpolated'], deficit_difference_L=deficit_difference,
            deficit_tolerance_L=tolerance, prediction=expected, measured=actual, possible_causes=possible_causes))
    return dict(consistent=all(r['consistent'] for r in rows), patients=rows,
                inconsistent_patient_ids=[r['patient_id'] for r in rows if not r['consistent']],
                measured_deaths=sum(v['death'] for v in measured.values()) if all(v['complete'] for v in measured.values()) else None,
                measured_deficit_L=sum(v['deficit_L'] for v in measured.values()) if all(v['deficit_L'] is not None for v in measured.values()) else None)


def verify_run(directory, *, reference_dir):
    # Importing this module does not initialize Pulse; native execution is only here.
    from core301.agent_chain import bridge
    from core301.agent_chain.timeline import build_timeline
    from core301.agent_chain.outcomes import patient_outcome
    from core301.dispatch.minimal.api import requirement

    directory = Path(directory)
    read = lambda name: json.loads((directory / name).read_text())
    context, schedule, specs, prediction = (read(name) for name in ('context.json', 'schedule.json', 'patient_specs.json', 'prediction.json'))
    validation = validate_schedule(context, schedule)
    write_json(directory / 'validation.json', validation)
    if validation['conflicts']:
        raise ValueError('Solver error: schedule conflicts; see validation.json')
    with (Path(reference_dir) / 'samples.csv').open() as handle:
        reference = minute_values(list(csv.DictReader(handle)), 'CardiacOutput_L_min', None, False)
    if None in reference:
        raise ValueError('Healthy reference is incomplete')
    pulse_dir = directory / 'pulse'
    pulse_dir.mkdir(exist_ok=False)
    input_dir = pulse_dir / 'input'
    input_dir.mkdir()
    write_json(input_dir / 'patient_specs.json', specs)
    timeline = build_timeline(context['patients'], context, schedule)
    write_json(pulse_dir / 'timeline.json', timeline)
    records = bridge.execute_all(context['patients'], timeline, pulse_dir, native=True, horizon_min=120.0, dataset_dir=input_dir)
    measured = {}
    for patient in context['patients']:
        pid, arrival = patient['patient_id'], patient['arrival_time_min']
        record = records[pid]
        outcome = patient_outcome(record, 120.0)
        terminal = outcome['terminal_event']
        terminal_global = terminal['time_min'] if terminal else None
        terminal_relative = terminal_global - arrival if terminal else None
        samples = [{**row, 'time_min': float(row['time_min']) - arrival} for row in record['samples']]
        series = cumulative_deficit(reference, minute_values(samples, 'CardiacOutput_L_min', terminal_relative, True))
        complete = outcome['window_status'] in ('complete', 'complete_terminal') and not any(outcome.get(k) for k in ('engine_failure', 'injury_unsupported', 'treatment_incomplete'))
        deviations = []
        selected = schedule['selections'].get(pid)
        if selected:
            plan = next(p for p in patient['candidate_plans'] if p['plan_id'] == selected)
            ends = {op['action_id']: op['end_min'] for op in schedule['operations'] if op['patient_id'] == pid}
            offset, first = 0, ends[plan['actions'][0]['action_id']]
            for action in plan['actions'][1:]:
                offset += requirement(context['action_mapping'], action, access_mode='new', mode='start')['duration_min']
                gap = ends[action['action_id']] - first - offset
                if gap:
                    deviations.append(gap)
        measured[pid] = dict(death=int(terminal_global is not None and terminal_global <= 120),
            terminal_global_min=terminal_global, terminal_min=terminal_relative,
            deficit_L=series[120 - int(arrival)] if complete else None, complete=complete,
            followup_deviations_min=deviations, outcome=outcome)
    write_json(pulse_dir / 'outcomes.json', measured)
    comparison = compare(prediction, measured)
    write_json(directory / 'comparison.json', comparison)
    return comparison
