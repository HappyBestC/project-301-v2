"""Final restricted N1 technical interpretation and E1 local mechanism rule.

This tightens the draft evidence checker; systemic risk remains independent.
"""
from core301.pulse.v2.hemothorax_endpoint_review import review_endpoints,FIXED
N1_VERSION='301.v2.hemothorax.N1.1'
E1_VERSION='301.v2.hemothorax.E1.1'

def review_fixed_endpoints(samples,*,configuration,safety_events,physiology_complete):
    r=review_endpoints(samples,configuration=configuration,safety_events=safety_events,physiology_complete=physiology_complete)
    r.update(n1_version=N1_VERSION,e1_version=E1_VERSION,
             admission='NOT_EVALUATED_BY_NUMERIC_RULE',safety_disposition='SEPARATE_ENGINEERING_SAFETY_GATE')
    # Exact native integer clock coverage is part of the new route's contract;
    # the historical draft and all historical observations remain unchanged.
    if 'INVALID_OBSERVATION' in r['problems']:return r
    if samples:
        if any(x.get('side')!='Left' for x in samples):r['problems'].append('WRONG_NATIVE_SIDE')
        if any(x.get('residual_blood_volume_mL',{}).get('value') is not None and x['residual_blood_volume_mL']['value']<-.01 for x in samples):
            r['problems'].append('TRAJECTORY_OVERSHOOT_OUT_OF_SCOPE')
        times=[x.get('simulation_time_s',-1) for x in samples]
        if any(not any(abs(t-second)<1e-6 for t in times) for second in range(660,961)):
            r['problems'].append('MISSING_ABSOLUTE_INTEGER_SAMPLE')
        if not any(660.02-1e-6<=t<=661+1e-6 and x.get('tube_action_active') and not x.get('source_action_active') for t,x in zip(times,samples)):
            r['problems'].append('TUBE_START_NOT_OBSERVED')
    if r['problems']:r.update(n1_consistent=False,local_control_supported=False)
    r['numeric_interpretation_only']=True
    return r
