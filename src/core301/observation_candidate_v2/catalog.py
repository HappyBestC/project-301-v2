"""Exact native sources; reuses the frozen request registry without modifying it."""
from core301.pulse.observation_projector import REQUESTS, BASIC
from core301.pulse.v2.exposure_session import EXPOSURE_REQUESTS
from core301.runtime.v2_1.native_backend import COMMON
from core301.pulse.v2.hemothorax_session import DRAIN_REQUESTS
VERSION='301.patient_observation.candidate.v2.1'
AGENT={k:{'unit':v[2] or '1','request':dict(zip(('Category','PropertyName','Unit','CompartmentName','SubstanceName'),v)),'raw_group':'values','raw_key':k} for k,v in REQUESTS.items() if not k.startswith('neurologic.')}
EXTRA={'laboratory.aorta_carboxyhemoglobin_concentration':'aorta_cohb_g_dL','laboratory.aorta_sodium_concentration':'aorta_sodium_mEq_L'}
for k,raw in EXTRA.items():
 q=dict(EXPOSURE_REQUESTS)[raw];AGENT[k]={'unit':q['Unit'],'request':q,'raw_group':'diagnostics','raw_key':raw}
INTERNAL={k:{'unit':q.get('Unit','1'),'request':q} for k,q in COMMON+DRAIN_REQUESTS}
CONDITIONAL=frozenset(AGENT)-frozenset(BASIC)
PRIMARY={
'external_hemorrhage':['vitals.heart_rate','vitals.systolic_arterial_pressure','vitals.mean_arterial_pressure','circulation.cardiac_output','laboratory.hemoglobin_concentration'],
'abdominal_internal_hemorrhage':['vitals.heart_rate','vitals.systolic_arterial_pressure','vitals.mean_arterial_pressure','circulation.cardiac_output','laboratory.hemoglobin_concentration'],
'open_pneumothorax':['vitals.respiration_rate','vitals.pulse_oximetry','laboratory.arterial_oxygen_pressure','respiratory.tidal_volume'],
'closed_tension_pneumothorax':['vitals.respiration_rate','vitals.pulse_oximetry','laboratory.arterial_oxygen_pressure','respiratory.tidal_volume'],
'hemothorax':['vitals.pulse_oximetry','laboratory.arterial_oxygen_pressure','respiratory.tidal_volume','vitals.mean_arterial_pressure','laboratory.hemoglobin_concentration'],
'respiratory_muscle_impairment':['vitals.respiration_rate','respiratory.tidal_volume','laboratory.arterial_carbon_dioxide_pressure','laboratory.blood_ph','vitals.pulse_oximetry'],
'impaired_alveolar_exchange':['vitals.pulse_oximetry','laboratory.arterial_oxygen_pressure','respiratory.inspired_oxygen_fraction','laboratory.arterial_carbon_dioxide_pressure','laboratory.blood_ph'],
'dehydration':['vitals.heart_rate','vitals.mean_arterial_pressure','circulation.cardiac_output','laboratory.hemoglobin_concentration','laboratory.aorta_sodium_concentration'],
'carbon_monoxide_exposure':['laboratory.aorta_carboxyhemoglobin_concentration','laboratory.arterial_oxygen_pressure'],
'environmental_hypoxia':['vitals.pulse_oximetry','laboratory.arterial_oxygen_pressure','respiratory.inspired_oxygen_fraction','vitals.heart_rate']}
MECHANISM={
'external_hemorrhage':['diagnostic.TotalHemorrhageRate','diagnostic.TotalHemorrhagedVolume','diagnostic.BloodVolume'],
'abdominal_internal_hemorrhage':['diagnostic.TotalHemorrhageRate','diagnostic.AbdominalCavityVolume','diagnostic.BloodVolume'],
'open_pneumothorax':['left_pleural_volume_mL','left_pleural_pressure_cmH2O'],
'closed_tension_pneumothorax':['left_pleural_volume_mL','left_pleural_pressure_cmH2O'],
'hemothorax':['residual_blood_volume_mL','source_flow_mL_s','tube_flow_mL_min'],
'respiratory_muscle_impairment':['alveolar_ventilation_L_min'],
'impaired_alveolar_exchange':['oxygen_saturation','alveolar_ventilation_L_min'],
'dehydration':['total_fluid_mL','diagnostic.BloodVolume','aorta_sodium_mEq_L'],
'carbon_monoxide_exposure':['aorta_co_saturation','aorta_cohb_g_dL','oxygen_saturation','ambient_co_fraction'],
'environmental_hypoxia':['ambient_oxygen_fraction','oxygen_saturation']}
MAPPING={k:{'primary_metrics':v,'supporting_metrics':['laboratory.lactate_concentration'],'safety_metrics':['vitals.heart_rate','vitals.mean_arterial_pressure','laboratory.arterial_carbon_dioxide_pressure','laboratory.blood_ph','aorta_sodium_mEq_L'],'mechanism_evidence':MECHANISM[k],'non_metric_evidence':['native_events','action_receipts','source_snapshots'],'observation_layer':'primary/supporting Agent subject to grants; diagnostics and nonmetric evidence evaluator only','evidence_status':'historical native replay; availability is branch/time dependent'} for k,v in PRIMARY.items()}
