#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/activate.sh
mkdir -p validation
python -m pytest -q tests/complete_dispatch tests/shared_dispatch tests/shared_resources tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -p no:cacheprovider --junitxml=validation/m2_baseline.xml | tee validation/m2_baseline.log
python -m pytest -q tests -m 'not integration' -p no:cacheprovider --junitxml=validation/all_unit.xml | tee validation/all_unit.log
for module in shared_resources.demo shared_demo complete_demo; do
  python -m "core301.dispatch.$module" > "validation/$module.jsonl"
done
python scripts/verify_baseline.py > validation/baseline_integrity.json
python scripts/check_demos.py > validation/demo_checks.json
python scripts/pulse_smoke.py > validation/pulse_smoke.log
(cd /tmp && "$VIRTUAL_ENV/bin/python" -IB "$VIRTUAL_ENV/../scripts/check_independence.py") > validation/independence.json
