"""Backend audit logic tests; fake values are not physiology evidence."""
import copy,json
from pathlib import Path
import pytest
from core301.pulse.v2.albuterol import fixed_steps,spontaneous_candidate_steps,delivery_evidence,log_times,AUDIT_REQUESTS


def state():
 return {'inhaler':{'Common':{'State':'Off'}},'airway_mode':'Free','actions':{},
         'diagnostics':{'diagnostic.Albuterol.LeftAlveoli.MassDeposited':2.0}}


def test_candidate_matches_local_official_scenario_exactly():
 path=Path(__file__).resolve().parents[2]/'engine-stable/data/human/adult/scenarios/drug/Albuterol.json'
 expected=json.loads(path.read_text())['AnyAction'][1:3]
 assert fixed_steps()==expected
 changed=fixed_steps();changed[0].clear();assert fixed_steps()==expected


def test_spontaneous_candidate_is_explicit_and_does_not_modify_original():
 original=copy.deepcopy(fixed_steps())
 new=spontaneous_candidate_steps()
 assert new[0]==original[0]
 assert new[1]['PatientAction']['ConsciousRespiration']['Command']==[{'UseInhaler':{}}]
 assert fixed_steps()==original


def test_backend_mass_request_uses_actual_native_compartment_name():
 request=next(req for key,req in AUDIT_REQUESTS if key.endswith('.Mass'))
 assert request['CompartmentName']=='InhalerMouthpiece'


def test_actual_log_times_are_required():
 assert log_times('[INFO] [183.08(s)] Inhaler actuated!','Inhaler actuated!')==[183.08]
 assert log_times('Inhaler actuated! without timestamp','Inhaler actuated!')==[]


@pytest.mark.parametrize('missing',['log','mass','removal','free','off','commands'])
def test_acceptance_or_incomplete_evidence_cannot_be_completed(missing):
 s=state();log='[INFO] [183.08(s)] Inhaler actuated!\n[INFO] [202(s)] Inhaler removed!'
 if missing=='log':log=''
 if missing=='mass':s['diagnostics']={}
 if missing=='removal':log=log.splitlines()[0]
 if missing=='free':s['airway_mode']='Inhaler'
 if missing=='off':s['inhaler']['Common']['State']='On'
 if missing=='commands':s['actions']['ConsciousRespiration']=[{'Command':[{}]}]
 lifecycle,evidence=delivery_evidence(s,log,180)
 assert lifecycle!='COMPLETED'
 assert evidence['clinical_recovery_claimed'] is False


def test_configuration_and_breathing_accepted_is_only_awaiting_trigger():
 s=state();s['diagnostics']={};s['actions']['ConsciousRespiration']=[{'Command':[{}]}]
 status,proof=delivery_evidence(s,'[INFO] [181(s)] configuration processed',180)
 assert status=='ACTIVE' and proof['delivery_phase']=='awaiting_actual_trigger'
 assert proof['actuation_count']==0


def test_single_trigger_mass_removal_and_command_completion():
 status,proof=delivery_evidence(state(),'[INFO] [183.08(s)] Inhaler actuated!\n[INFO] [202(s)] Inhaler removed!',180)
 assert status=='COMPLETED' and proof['actuation_count']==1 and proof['actual_drug_presence_confirmed']
 assert proof['completion_scope']=='single_administration_and_device_sequence'


def test_multiple_native_administrations_remain_unknown():
 status,proof=delivery_evidence(state(),'[INFO] [183(s)] Inhaler actuated!\n[INFO] [243(s)] Inhaler actuated!',180)
 assert status=='UNKNOWN' and proof['error']=='UNEXPECTED_REPEAT_ADMINISTRATION'


def test_old_trigger_does_not_confirm_new_request():
 status,proof=delivery_evidence(state(),'[INFO] [3(s)] Inhaler actuated!\n[INFO] [23(s)] Inhaler removed!',180)
 assert status=='UNKNOWN' and proof['actuation_count']==0


def test_native_ignored_repeat_is_not_a_successful_new_dose():
 log='[INFO] [183(s)] Inhaler actuated!\n[ERROR] [243(s)] Already processing a Substance Inhalation, ignoring this command'
 status,proof=delivery_evidence(state(),log,180)
 assert status=='UNKNOWN' and proof['error']=='NATIVE_INHALATION_COMMAND_IGNORED'


def test_hemothorax_null_flow_and_negative_residual_are_preserved():
 from core301.pulse.v2.specialty_audit import hemothorax_evidence
 raw={'diagnostic.LeftHemothorax.TotalBloodVolume':-.003148148,'diagnostic.LeftHemothorax.FlowRate':None}
 proof=hemothorax_evidence({'actions':{}},raw,'[INFO] [715.54(s)] Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.','Left')
 assert proof['source_flow_mL_s'] is None and not proof['source_flow_valid']
 assert proof['residual_volume_mL']==-.003148148 and proof['negative_native_residual']
 assert proof['auto_removal_observed'] and not proof['full_treatment_completed']
 assert not proof['authorized_observation_endpoint']


def test_no_tube_action_without_stop_evidence_is_not_auto_removal():
 from core301.pulse.v2.specialty_audit import hemothorax_evidence
 assert not hemothorax_evidence({'actions':{}},{},'','Left')['auto_removal_observed']


@pytest.mark.parametrize('volume,expected',[(425,'ACTIVE'),(0,'UNKNOWN'),(None,'UNKNOWN')])
def test_oxygen_state_requires_actual_device_and_valid_remaining_source(volume,expected):
 from core301.pulse.v2.specialty_audit import oxygen_evidence
 source={'Device':'NasalCannula','Flow':{'ScalarVolumePerTime':{'Value':.5,'Unit':'L/min'}}}
 if volume is not None:source['Volume']={'ScalarVolume':{'Value':volume,'Unit':'L'}}
 proof=oxygen_evidence({'actions':{'SupplementalOxygen':[source]},'airway_mode':'NasalCannula'})
 assert proof['state']==expected and not proof['treatment_completed']
