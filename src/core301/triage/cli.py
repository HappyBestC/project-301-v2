"""Triage a stored scenario without starting Pulse or requesting a model."""
import argparse
import json
from pathlib import Path

from core301.agent_chain.audit import write_json
from core301.agent_chain.scenarios import SCENARIOS, scenario_paths
from core301.dispatch.minimal import api
from .service import triage_cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=tuple(SCENARIOS), required=True)
    args = parser.parse_args(argv)
    dataset = scenario_paths(args.scenario)['dataset_dir']
    result = triage_cases(api.load_cases(dataset), api.read(dataset / 'patient_specs.json'))
    write_json(Path('triage.json'), result)
    for patient in result['patients']:
        inputs = patient['inputs']
        wounds = json.dumps(inputs['wounds'], ensure_ascii=False, allow_nan=False)
        print(f"{patient['patient_id']} wounds={wounds} HR={inputs['HR']} RR={inputs['RR']} "
              f"tag={patient['tag']} reason_code={patient['reason_code']} reason={patient['reason']}")
    print(json.dumps(result['summary'], ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
