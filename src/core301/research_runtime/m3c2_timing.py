"""Separate, discrete exploratory timing contract; default phase1 stays frozen."""
import math
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.runtime.v2.errors import V2Error
from core301.pulse.v2.protocol_book import PROFILE_VERSION, PATIENT_SHA256, STATE_SHA256

VERSION='301.research.dynamic_timing.m3c2.1'

def protocol(exploratory=False):
    return dict(protocol_id='m3c2_external_rightleg_delayed_control' if exploratory else 'phase1_frozen',
        protocol_version=VERSION if exploratory else PROFILE_VERSION,reference_protocol=PROFILE_VERSION,
        exploratory=exploratory,patient='StandardMale',patient_sha256=PATIENT_SHA256,state_sha256=STATE_SHA256,
        injury='external_hemorrhage',compartment='RightLeg',severity=.4,
        action='control_external_bleeding',parameter_policy='fixed_profile_no_overrides',
        injury_time_s=60,initial_decision_s=180,candidate_treatment_times_s=[180,181] if exploratory else [180],
        endpoint_s=480,sampling_interval_s=1,release_policy='first subsequent sample with source_control_confirmed',
        formal_evaluation='NOT_EVALUABLE',unknown_policy='halt and quarantine; no replay')

def time_allowed(now,exploratory=False):
    return math.isfinite(now) and any(abs(now-t)<=1e-6 for t in ([180,181] if exploratory else [180]))

class DynamicTimingCaseRuntime(CaseRuntime):
    def validate_treatment_timing(self,plan,source,now):
        if not time_allowed(now,True):raise V2Error('UNVALIDATED_TIMING','M3-C2 admits only discrete 180/181 exploratory times')
        if (self.mode!='research' or source.injury_type!='external_hemorrhage' or source.compartment!='RightLeg'
            or source.initial_severity!=.4 or len(plan.actions)!=1
            or plan.actions[0].action_type!='control_external_bleeding' or plan.actions[0].compartment!='RightLeg'):
            raise V2Error('DYNAMIC_SCOPE_REJECTED','Only the declared single-source fixed control plan is admitted')
        return {'protocol_version':VERSION,'reference_protocol':PROFILE_VERSION,'exploratory':True,
                'submitted_candidate_s':next(t for t in [180,181] if abs(now-t)<=1e-6),'formal_grade':None}
