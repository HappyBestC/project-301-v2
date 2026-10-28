import json,sys,traceback,hashlib,csv
from pathlib import Path
import PyPulse
ROOT=Path(__file__).resolve().parent
DATA=Path('/home/private/project-301/pulse/bin')
F=PyPulse.serialization_format.json

def scalar(t,v,u=None):
 d={'Value':v}
 if u:d['Unit']=u
 return {'Scalar'+t:d}
def pa(n,**kw):return {'PatientAction':{n:kw}}
def bolus(name='Epinephrine',dose=1.25,route='Intravenous'):
 return pa('SubstanceBolus',Substance=name,AdministrationRoute=route,AdministrationDuration=scalar('Time',2,'s'),Dose=scalar('Volume',1,'mL'),Concentration=scalar('MassPerVolume',dose,'ug/mL'))
def inf(rate=1):return pa('SubstanceInfusion',Substance='Epinephrine',Concentration=scalar('MassPerVolume',1,'ug/mL'),Rate=scalar('VolumePerTime',rate,'mL/min'),Volume=scalar('Volume',10,'mL'))
def saline():return pa('SubstanceCompoundInfusion',SubstanceCompound='Saline',BagVolume=scalar('Volume',250,'mL'),Rate=scalar('VolumePerTime',60,'mL/min'))
def oxy():return pa('SupplementalOxygen',Device='NasalCannula',Flow=scalar('VolumePerTime',3,'L/min'),Volume=scalar('Volume',100,'L'))
def mv():return pa('MechanicalVentilation',State='On',Pressure=scalar('Pressure',5,'cmH2O'),Flow=scalar('VolumePerTime',0,'L/min'))
REQUESTS=[('HeartRate','1/min'),('MeanArterialPressure','mmHg'),('SystolicArterialPressure','mmHg'),('RespirationRate','1/min'),('OxygenSaturation',None),('BloodVolume','mL'),('SedationLevel',None)]
req=[dict(Category='Physiology',PropertyName=p,**({'Unit':u} if u else {})) for p,u in REQUESTS]
for s in ['Epinephrine','Morphine']:req.append(dict(Category='Substance',SubstanceName=s,PropertyName='PlasmaConcentration',Unit='ug/mL'))
headers=['time_s']+[p for p,u in REQUESTS]+['Epinephrine_ug_mL','Morphine_ug_mL']
CASES={
'baseline':[], 'epi_low':[(0,bolus())], 'epi_high':[(0,bolus(dose=5))],
'saline':[(0,saline())], 'combo_AB':[(0,bolus()),(0,saline())], 'combo_BA':[(0,saline()),(0,bolus())],
'infusion_update_stop':[(0,inf()),(10,inf()),(20,inf(2)),(40,inf(0))],
'overlap':[(0,saline()),(20,oxy()),(40,pa('SupplementalOxygen',Device='None'))],
'bolus_overwrite':[(0,bolus()),(0,bolus(dose=5))],
'morphine':[(0,bolus('Morphine',1000))], 'multidrug':[(0,bolus()),(0,bolus('Morphine',1000))],
'airway_AB':[(0,oxy()),(0,mv())], 'airway_BA':[(0,mv()),(0,oxy())],
'unsupported_route':[(0,bolus(route='Intraosseous'))],
'dressing_without_injury':[(0,pa('ChestOcclusiveDressing',Side='Left',State='On'))],
'combo_high_AB':[(0,bolus(dose=5)),(0,saline())],
'combo_high_BA':[(0,saline()),(0,bolus(dose=5))],
'multidrug_high':[(0,bolus(dose=5)),(0,bolus('Morphine',1000))],
'hemorrhage_control':[(0,pa('Hemorrhage',Compartment='LeftLeg',Severity=scalar('0To1',0.2)))],
'hemorrhage_stop':[(0,pa('Hemorrhage',Compartment='LeftLeg',Severity=scalar('0To1',0.2))),(20,pa('Hemorrhage',Compartment='LeftLeg',Severity=scalar('0To1',0)))],
'chest_control':[(0,pa('TensionPneumothorax',Side='Left',Type='Open',Severity=scalar('0To1',0.3)))],
'chest_dressing':[(0,pa('TensionPneumothorax',Side='Left',Type='Open',Severity=scalar('0To1',0.3))),(20,pa('ChestOcclusiveDressing',Side='Left',State='On'))],
'invalid_missing_dose':[(0,pa('SubstanceBolus',Substance='Epinephrine',Concentration=scalar('MassPerVolume',1,'ug/mL')))],
'repeat_completed':[(0,bolus()),(10,bolus())],
}
def run(name):
 out=ROOT/'raw'/name;out.mkdir(parents=True,exist_ok=False)
 events=[];rows=[];e=PyPulse.Engine(PyPulse.model_type.human_adult_whole_body,str(DATA));e.log_to_console(False);e.set_log_filename(str(out/'pulse.log'))
 def snapshot(tag):
  state=json.loads(e.serialize_to_string(F)); sel={k:v for k,v in state.items() if 'Action' in k or k in ['AirwayMode','SimulationTime']}
  (out/(tag+'.json')).write_text(json.dumps(sel,indent=2));return sel
 def emit(x):
  events.append(x);(out/'events.json').write_text(json.dumps(events,indent=2))
 try:
  ok=e.serialize_from_file(str(DATA/'states/Soldier@0s.json'),json.dumps({'DataRequest':req}),F)
  emit({'initialize':ok,'module':PyPulse.__file__,'version':PyPulse.__version__})
  if not ok:raise RuntimeError('Soldier load failed')
  dt=e.get_timestep('s');emit({'dt_s':dt,'initial_patient':e.get_initial_patient(F)})
  schedule={}
  for t,a in CASES[name]:schedule.setdefault(round(t/dt),[]).append(a)
  end=1 if name.startswith('probe_') else (60 if 'airway' not in name else 0.1)
  rows.append(list(e.pull_data()));snapshot('initial')
  for step in range(round(end/dt)+1):
   if step in schedule:
    for idx,a in enumerate(schedule[step]):
     t=float(e.pull_data()[0]);ok=e.process_actions(json.dumps({'AnyAction':[a]}),F)
     emit({'submit_time_s':t,'action':a,'accepted':ok,'after_time_s':float(e.pull_data()[0])})
     snapshot(f'submit_{step}_{idx}')
   if step==round(end/dt):break
   ok=e.advance_timestep()
   if not ok:emit({'advance_failed_at_step':step});break
   if (step+1)%round(5/dt)==0 or step in schedule:
    rows.append(list(e.pull_data()));snapshot(f'advance_{step+1}')
  snapshot('final');emit({'loop_finished':True,'reached_requested_end':abs(float(e.pull_data()[0])-end)<dt/2,'final_time_s':float(e.pull_data()[0])})
 except Exception as ex:
  emit({'exception':repr(ex),'traceback':traceback.format_exc()})
 finally:
  with (out/'samples.csv').open('w') as f:
   w=csv.writer(f);w.writerow(headers);w.writerows(rows)
  e.clear()
 print(name,json.dumps(events[-1]),flush=True)
if __name__=='__main__':run(sys.argv[1])
