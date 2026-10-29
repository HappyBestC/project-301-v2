#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/activate.sh
validation_dir="${CORE301_VALIDATION_DIR:-validation}"
project301_validation_root="$PWD"
mkdir -p "$validation_dir/tmp" "$validation_dir/isolated"
export TMPDIR="$(cd "$validation_dir/tmp" && pwd)"
python -m pytest -q tests/complete_dispatch tests/shared_dispatch tests/shared_resources tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_audit.py -m 'not integration' -p no:cacheprovider --junitxml="$validation_dir/m2_baseline.xml" | tee "$validation_dir/m2_baseline.log"
python -m pytest -q tests -m 'not integration' -p no:cacheprovider --junitxml="$validation_dir/all_unit.xml" | tee "$validation_dir/all_unit.log"
for module in shared_resources.demo shared_demo complete_demo; do
  python -m "core301.dispatch.$module" > "$validation_dir/$module.jsonl"
done
python scripts/verify_baseline.py > "$validation_dir/baseline_integrity.json"
python scripts/check_demos.py > "$validation_dir/demo_checks.json"
python scripts/pulse_smoke.py > "$validation_dir/pulse_smoke.log"
(cd "$validation_dir/isolated" && python -IB "$project301_validation_root/scripts/check_independence.py") > "$validation_dir/independence.json"
