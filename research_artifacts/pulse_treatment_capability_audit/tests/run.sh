#!/bin/bash
set -u
source /home/private/project-301/activate-pulse.sh
cd /home/private/project-301-v2/research_artifacts/pulse_treatment_capability_audit/tests
for case in baseline epi_low epi_high saline combo_AB combo_BA infusion_update_stop overlap bolus_overwrite morphine multidrug airway_AB airway_BA unsupported_route dressing_without_injury repeat_completed; do
 timeout 90 python native_audit.py "$case" > "$case.stdout.log" 2>&1
 echo "$case exit=$?"
done
