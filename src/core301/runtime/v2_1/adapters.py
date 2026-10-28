"""Fixed payloads derived from the frozen adapters; no Agent native parameters."""
from core301.pulse.injury_adapter import scalar
from core301.pulse.v2.exposure_session import environment_action
from core301.pulse.treatment_adapter import TreatmentAdapter
from core301.contracts.treatment import TreatmentPlan
def action_payload(kind,pattern):
 if kind=='remove_from_exposure':return environment_action(0,.21)
 if kind.startswith('control_'):
  if kind=='control_hemothorax_bleeding':return {'PatientAction':{'Hemothorax':{'Side':'Left','Severity':scalar('0To1',0)}}}
  inside=kind=='control_internal_bleeding'
  return {'PatientAction':{'Hemorrhage':{'Type':'Internal' if inside else 'External','Compartment':'Spleen' if inside else 'RightLeg','Severity':scalar('0To1',0)}}}
 if kind=='supplemental_oxygen':return {'PatientAction':{'SupplementalOxygen':{'Device':'NasalCannula','Flow':scalar('VolumePerTime',.5,'L/min'),'Volume':scalar('Volume',425,'L')}}}
 action={'action_type':kind}
 if kind in ('occlusive_dressing','needle_decompression','chest_tube'):action['side']='Left'
 actions=([{'action_type':'intubation'}] if kind=='mechanical_ventilation' else [])+[action]
 return TreatmentAdapter().convert(TreatmentPlan(patient_id='composite-patient',actions=actions))[-1]
def kinds_for(pattern,branch):return [k for g in branch for k in pattern['treatment_bundles'][g]]
