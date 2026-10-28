"""Mechanism and safety are distinct; no invented clinical ranges or labels."""
from core301.runtime.v2.exposure_validation import HALT_EVENTS
from core301.pulse.v2.hemothorax_acceptance import review_fixed_endpoints, FIXED
from core301.runtime.v2.restricted_registry import VERSION

TARGET_EVENTS=frozenset({'Hypoxia','Tachycardia'})
CYCLE_EVENTS=frozenset({'StartOfCardiacCycle','StartOfInhale','StartOfExhale'})

def safety_check(kind, history, *, risk_conformance=None):
    events=set().union(*(set(x.native_events) for x in history)) if history else set()
    final=set(history[-1].native_events) if history else set()
    permitted=CYCLE_EVENTS | (TARGET_EVENTS if kind=='environmental_hypoxia' else frozenset({'MinimalHemothorax'}) if kind=='hemothorax' else frozenset())
    accepted=frozenset({'Hypernatremia'}) if risk_conformance and risk_conformance['passed'] and kind in ('hemothorax','carbon_monoxide_exposure') else frozenset()
    reasons=[]
    if not history:reasons.append('MISSING_OBSERVATION')
    if events & HALT_EVENTS:reasons.append('CRITICAL_EVENT')
    if events-permitted-accepted:reasons.append('UNRESOLVED_NATIVE_EVENTS')
    if final-CYCLE_EVENTS-accepted:reasons.append('RESIDUAL_NATIVE_EVENTS')
    if kind in ('hemothorax','carbon_monoxide_exposure') and (not risk_conformance or not risk_conformance['passed']):reasons.append('RISK_SCOPE_NOT_VERIFIED')
    for x in history:
        if x.aorta_sodium_mEq_L.status!='available' or x.aorta_sodium_mEq_L.value is None:reasons.append('MISSING_SODIUM')
        p=x.patient_observation.model_dump()
        from core301.runtime.v2.exposure_validation import PUBLIC_FIELDS
        for path in PUBLIC_FIELDS:
            g,f=path.split('.');m=(p.get(g) or {}).get(f)
            if not m or m['status']!='available' or m['value'] is None or m['observed_at_s']!=x.patient_observation.simulation_time_s:
                reasons.append('MISSING_PHYSIOLOGY')
        if kind!='hemothorax':
            for name in ('aorta_co_saturation','aorta_cohb_g_dL','oxygen_saturation','aorta_sodium_mEq_L','ambient_co_fraction','ambient_oxygen_fraction'):
                m=getattr(x.specialty,name)
                if m.status!='available' or m.value is None:reasons.append('MISSING_DIAGNOSTIC')
    return {'passed':not reasons,'reasons':sorted(set(reasons)),'all_event_names':sorted(events),'final_events':sorted(final),
            'accepted_risk_events':sorted(events & accepted),'risk_conformance':risk_conformance,
            'scope':'fixed engineering window only; no clinical certification'}

def mechanism_check(kind, history, control):
    if not history or not control:return {'passed':False,'reason':'MISSING_PAIR'}
    a,b,c=history[0],history[-1],control[-1]
    if kind=='hemothorax':
        r=review_fixed_endpoints([x.specialty.model_dump() for x in history],configuration=FIXED,
            safety_events=b.native_events,physiology_complete=True)
        r['n1_version']='301.v2.hemothorax.N1.1';r['e1_version']='301.v2.hemothorax.E1.1'
        r['passed']=r['local_control_supported'] and c.specialty.residual_blood_volume_mL.value>a.specialty.residual_blood_volume_mL.value
        return r
    sa,sb,sc=a.specialty,b.specialty,c.specialty
    environment=sb.ambient_co_fraction.value==0 and sb.ambient_oxygen_fraction.value==.21
    if kind=='carbon_monoxide_exposure':
        ok=environment and 0<sb.aorta_co_saturation.value<sa.aorta_co_saturation.value<sc.aorta_co_saturation.value and sb.aorta_cohb_g_dL.value<sc.aorta_cohb_g_dL.value
    else:
        pa,pb,pc=a.patient_observation,b.patient_observation,c.patient_observation
        ok=(environment and sa.ambient_oxygen_fraction.value==.12 and sc.ambient_oxygen_fraction.value==.12
            and TARGET_EVENTS<=set(a.native_events) and TARGET_EVENTS<=set(c.native_events)
            and not TARGET_EVENTS.intersection(b.native_events)
            and pb.laboratory.arterial_oxygen_pressure.value>pc.laboratory.arterial_oxygen_pressure.value
            and pb.vitals.heart_rate.value<pc.vitals.heart_rate.value
            and sb.oxygen_saturation.value>sc.oxygen_saturation.value)
    return {'passed':bool(ok),'version':VERSION,'clinical_cure':False}
