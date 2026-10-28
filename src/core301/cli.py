import argparse
import json
from pathlib import Path
from core301.runtime.case_runtime import CaseRuntime
from core301.paths import PROJECT_ROOT
from core301.contracts.casualty import CasualtyInput


def main():
    parser = argparse.ArgumentParser(description="301 Frozen v1 deterministic Pulse loop")
    parser.add_argument("--casualty", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--provider", choices=("manual", "llm"), default="manual")
    parser.add_argument("--fixtures", action="store_true", help="run the three milestone fixtures sequentially")
    parser.add_argument("--before-s", type=float, default=60.0)
    parser.add_argument("--after-s", type=float, default=60.0)
    parser.add_argument("--runs-dir", type=Path, default=PROJECT_ROOT / "runs")
    args = parser.parse_args()
    if args.provider == "llm" and args.plan:
        parser.error("--plan is only supported by --provider manual")
    fixtures = Path(__file__).parent / "fixtures"
    default_casualties = PROJECT_ROOT / "patient-test/casualties_v1.json"
    if not default_casualties.is_file():
        default_casualties = PROJECT_ROOT / "src/core301/fixtures/casualties_v1.json"
    if args.fixtures:
        if args.casualty or args.plan:
            parser.error("--fixtures cannot be combined with custom input files")
        cases = json.loads(default_casualties.read_text())
        plans = [{"patient_id": c["patient_id"], "actions": []} for c in cases]
    elif args.provider == "llm":
        data = json.loads((args.casualty or default_casualties).read_text())
        cases = data if isinstance(data, list) else [data]
        plans = [None] * len(cases)
    else:
        if args.provider == "manual" and bool(args.casualty) != bool(args.plan):
            parser.error("--casualty and --plan must be provided together")
        cases = [json.loads((args.casualty or fixtures / "first_case.json").read_text())]
        plans = ([json.loads((args.plan or fixtures / "first_plan.json").read_text())]
                 if args.provider == "manual" else [None])
    # Validate the entire batch before making API requests or starting Pulse.
    for case in cases:
        CasualtyInput.model_validate(case)
    provider = None
    if args.provider == "llm":
        from core301.agent.llm_provider import LLMTreatmentProvider
        provider = LLMTreatmentProvider()
    for case, plan in zip(cases, plans):
        runtime = CaseRuntime(case["patient_id"], runs_dir=args.runs_dir)
        print(runtime.run_once(case, plan if provider is None else None, provider=provider,
                               before_s=args.before_s, after_s=args.after_s))


if __name__ == "__main__":
    main()
