#!/bin/bash
source /home/private/project-301/activate-pulse.sh
cd /home/private/project-301-v2/research_artifacts/pulse_treatment_capability_audit/tests
for case in probe_IA probe_IM probe_mv probe_intubation probe_needle probe_tube probe_blood probe_bvm; do
 timeout 30 python probes.py "$case" > "$case.stdout.log" 2>&1
 echo "$case exit=$?"
done
