"""Dimensional diagnostic only. Never normalizes a value or grants admission."""
def review_overshoot(raw_volume_mL, *, dt_s, flow_mL_min, source_active, tube_active, auto_stop_seen, previous_stopped_volume=None):
    bound=flow_mL_min/60*dt_s
    fixed=dt_s==.02 and flow_mL_min==30
    drift=previous_stopped_volume is not None and raw_volume_mL is not None and raw_volume_mL<previous_stopped_volume
    eligible=(fixed and raw_volume_mL is not None and not source_active and not tube_active and auto_stop_seen and not drift)
    within=eligible and -bound<=raw_volume_mL<0
    return {'raw_volume_mL':raw_volume_mL,'step_bound_mL':bound,'fixed_profile':fixed,
            'negative_drift':drift,'consistent_with_single_step_overshoot':bool(within),
            'classification':'single_step_overshoot_candidate' if within else 'unresolved_negative' if raw_volume_mL is not None and raw_volume_mL<0 else 'unavailable' if raw_volume_mL is None else 'native_nonnegative',
            'normalized_volume_mL':None,'efficacy_passed':False,'research_rule_approval':'PENDING'}
