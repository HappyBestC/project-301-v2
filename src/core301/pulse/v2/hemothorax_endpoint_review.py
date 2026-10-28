"""N1/E1 evidence checks only. A review is never a research approval."""
import math
from core301.contracts.v2.hemothorax_observation import HemothoraxObservation

N1_VERSION='301.v2.hemothorax.N1.proposal.1'
E1_VERSION='301.v2.hemothorax.E1.proposal.1'
FIXED={'pulse_version':'4.3.2','dt_s':.02,'side':'Left','severity':.8,'tube_flow_mL_min':30,
       'source_control_s':660,'tube_start_s':660.02,'end_s':960}

def review_endpoints(samples,*,configuration,safety_events,physiology_complete):
    """Require longitudinal native evidence, not just a plausible negative scalar.

    Samples are trusted backend observations, not Agent submissions. Raw samples
    and events remain external evidence; this function does not normalize them.
    Numeric/time tolerances express machine precision, never clinical thresholds.
    """
    result={'n1_version':N1_VERSION,'e1_version':E1_VERSION,'n1_consistent':False,'local_control_supported':False,
            'admission':'PENDING_RESEARCH_RULE_APPROVAL','goal_passed':False,'normalized_volume_mL':None,
            'production_enabled':False,'problems':[],'safety_events':safety_events,
            'safety_disposition':'UNRESOLVED_EVENTS' if safety_events else 'CRITERIA_NOT_APPROVED'}
    bad=result['problems']
    if configuration!=FIXED:bad.append('CONFIGURATION_OUT_OF_SCOPE')
    try:obs=[HemothoraxObservation.model_validate(x) for x in samples]
    except (ValueError,TypeError):bad.append('INVALID_OBSERVATION');return result
    if len(obs)<3:bad.append('INSUFFICIENT_LONGITUDINAL_EVIDENCE');return result
    first,last=obs[0],obs[-1]
    if not first.source_action_active or first.tube_action_active:
        bad.append('PRETREATMENT_SOURCE_NOT_CONFIRMED')
    if any(o.source_action_active for o in obs[1:]):
        bad.append('POST_CONTROL_SOURCE_ACTIVE')
    if any((o.patient_id,o.session_epoch,o.side)!=(first.patient_id,first.session_epoch,first.side) for o in obs):bad.append('IDENTITY_OR_EPOCH_MISMATCH')
    if any(b.simulation_time_s<=a.simulation_time_s for a,b in zip(obs,obs[1:])):bad.append('NONMONOTONIC_TIME')
    if abs(first.simulation_time_s-660)>1e-6 or abs(last.simulation_time_s-960)>1e-6:bad.append('INCOMPLETE_FIXED_WINDOW')
    if any(o.residual_blood_volume_mL.value is None for o in obs):bad.append('MISSING_VOLUME');return result
    initial=first.residual_blood_volume_mL.value;raw=last.residual_blood_volume_mL.value
    active=[o for o in obs if o.tube_action_active]
    if initial<=0 or raw>=initial:bad.append('NO_OBSERVED_DRAINAGE')
    if not active or any(o.tube_flow_mL_min!=30 or o.source_action_active for o in active):bad.append('ACTIVE_TUBE_EVIDENCE_MISSING_OR_CONFLICTING')
    if last.source_action_active or last.tube_action_active:bad.append('SOURCE_OR_TUBE_STILL_ACTIVE')
    events=[e for o in obs for e in o.events if 'Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.' in e.raw_log_line]
    if not events:bad.append('NO_NATIVE_AUTO_STOP')
    else:
        stop=min(e.native_time_s for e in events)
        if not active or not active[0].simulation_time_s<stop:bad.append('NO_PRIOR_ACTIVE_TUBE')
        after=[o for o in obs if o.simulation_time_s>=stop]
        if len(after)<2:bad.append('NO_POST_STOP_FOLLOWUP')
        elif any(o.source_action_active or o.tube_action_active or o.residual_blood_volume_mL.value!=after[0].residual_blood_volume_mL.value for o in after):bad.append('POST_STOP_ACTIVITY_OR_VOLUME_DRIFT')
    if not math.isfinite(raw) or raw<-.01:bad.append('NEGATIVE_OUTSIDE_SINGLE_TICK')
    if raw>0:bad.append('RESIDUAL_VOLUME_REMAINS')
    technical_ok=not bad
    result['n1_consistent']=technical_ok and -.01<=raw<0
    result['local_control_supported']=technical_ok and (raw==0 or result['n1_consistent'])
    result['raw_final_volume_mL']=raw
    if not physiology_complete:bad.append('MISSING_SYSTEMIC_OBSERVATION')
    # Local evidence does not override systemic safety or grant either rule.
    return result
