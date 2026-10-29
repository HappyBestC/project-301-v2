"""Offline solve / explicit native verify commands."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from core301.paths import PROJECT_ROOT
from core301.dispatch.minimal.validation import validate_schedule
from .scenario import load_scenario
from .tables import TableStore, prepare_costs
from .verify import write_json, verify_run


def run_directory(run_id):
    if not run_id or Path(run_id).name != run_id or run_id in ('.', '..'):
        raise ValueError('run-id must be a single directory name')
    return PROJECT_ROOT / 'runs' / 'standard_answer' / run_id


def solve_run(args):
    from .model import StandardModel
    from .solve import Parameters, optimize, insertion_seed, hint_decisions, complete_hint
    from .diagnose import DiagnosisPending, InsertionImprovement, diagnose_unscheduled
    from .export import export_schedule, predict

    parameters = Parameters(args.time_limit_s, args.workers, args.seed, args.max_followup_gap)
    context, specs, typical, definition = load_scenario(args.scenario)
    store = TableStore(args.tables)
    # Both modes require true-severity tables for evaluation, even if optimization is typical.
    true_costs, true_untreated, true_warnings = prepare_costs(context, specs, store)
    costs, untreated, warnings = ((true_costs, true_untreated, true_warnings) if args.table_mode == 'oracle'
                                   else prepare_costs(context, typical, store))
    directory = run_directory(args.run_id)
    directory.mkdir(parents=True, exist_ok=False)
    store.save_snapshot(directory / 'tables')
    write_json(directory / 'context.json', context)
    write_json(directory / 'patient_specs.json', list(specs.values()))
    metadata = dict(scenario=definition, table_mode=args.table_mode, tables_dir=str(Path(args.tables).resolve()),
                    table_sha256=store.hashes, table_warnings=warnings, true_table_warnings=true_warnings,
                    parameters=asdict(parameters), unscheduled_checks={})
    write_json(directory / 'solve.json', metadata)
    model = StandardModel(context, costs, untreated, max_followup_gap=parameters.max_followup_gap)
    metadata['incumbent_seed'] = insertion_seed(model, costs, untreated, parameters)
    def progress(records):
        metadata['stages'] = records
        write_json(directory / 'solve.json', metadata)
        print(f"{records[-1]['name']}: {records[-1]['status']} objective={records[-1]['objective']}", flush=True)
    while True:
        solver, result = optimize(model, parameters, on_stage=progress)
        metadata.update(result)
        write_json(directory / 'solve.json', metadata)
        if solver is None:
            raise ValueError('Optimization did not complete all three stages; see solve.json')
        try:
            diagnoses = diagnose_unscheduled(model, solver, costs, untreated, parameters)
        except InsertionImprovement as exc:
            metadata.setdefault('insertion_improvements', []).append(dict(solve=result, checks=exc.checks))
            model = StandardModel(context, costs, untreated, max_followup_gap=parameters.max_followup_gap)
            hint_decisions(model, exc.values)
            complete_hint(model, parameters)
            continue
        except DiagnosisPending as exc:
            metadata.update(unscheduled_checks=exc.checks, pending_questions=[str(exc)])
            write_json(directory / 'solve.json', metadata)
            raise
        break
    metadata['unscheduled_checks'] = diagnoses
    write_json(directory / 'solve.json', metadata)
    schedule = export_schedule(model, solver, diagnoses)
    validation = validate_schedule(context, schedule)
    write_json(directory / 'validation.json', validation)
    if validation['conflicts']:
        metadata['solver_error'] = validation['conflicts']
        write_json(directory / 'solve.json', metadata)
        raise ValueError('Solver error: modeled schedule has conflicts; see validation.json')
    write_json(directory / 'schedule.json', schedule)
    write_json(directory / 'prediction.json', predict(context, specs, schedule, store))
    return dict(run_dir=str(directory), objective=result['objective'], conflicts=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    solve = commands.add_parser('solve')
    solve.add_argument('--scenario', default='run_002', help='run_002 or a severity-override JSON file')
    solve.add_argument('--tables', type=Path, default=PROJECT_ROOT / 'runs/curve_probe_001/tables')
    solve.add_argument('--table-mode', choices=('oracle', 'typical'), default='oracle')
    solve.add_argument('--run-id', required=True)
    solve.add_argument('--time-limit-s', type=float, default=600)
    solve.add_argument('--workers', type=int, default=8)
    solve.add_argument('--seed', type=int, default=0)
    solve.add_argument('--max-followup-gap', type=int, default=0)
    verify = commands.add_parser('verify')
    verify.add_argument('--run-id', required=True)
    verify.add_argument('--reference-dir', type=Path, default=PROJECT_ROOT / 'runs/curve_probe_001/runs/reference_healthy')
    args = parser.parse_args(argv)
    try:
        result = solve_run(args) if args.command == 'solve' else verify_run(run_directory(args.run_id), reference_dir=args.reference_dir)
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(result)
    return 0 if args.command == 'solve' or result['consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
