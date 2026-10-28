#!/bin/bash
set -u
source /home/private/project-301/activate-pulse.sh
cd /home/private/project-301-v2/research_artifacts/pulse_treatment_capability_audit/tests
for case in combo_high_AB combo_high_BA multidrug_high hemorrhage_control hemorrhage_stop chest_control chest_dressing invalid_missing_dose; do
 timeout 90 python native_audit.py "$case" > "$case.stdout.log" 2>&1
 echo "$case exit=$?"
done
