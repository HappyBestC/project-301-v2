import native_audit as n
from pathlib import Path
import json
s=n.scalar;p=n.pa
cases={
'probe_IA':[(0,n.bolus(route='Intraarterial'))],
'probe_IM':[(0,n.bolus(route='Intramuscular'))],
'probe_mv':[(0,n.mv()),(0.1,p('MechanicalVentilation',State='Off'))],
'probe_intubation':[(0,p('Intubation',Type='Tracheal')),(0.1,p('Intubation',Type='Oropharyngeal')),(0.2,p('Intubation',Type='Off'))],
'probe_needle':[(0,p('TensionPneumothorax',Type='Closed',Side='Left',Severity=s('0To1',0.3))),(0,p('NeedleDecompression',Side='Left',State='On')),(0.1,p('NeedleDecompression',Side='Left',State='Off'))],
'probe_tube':[(0,p('TubeThoracostomy',Side='Left')),(0.1,p('TubeThoracostomy',Side='Left',FlowRate=s('VolumePerTime',0.1,'mL/s'))),(0.2,p('TubeThoracostomy',Side='Left'))],
'probe_blood':[(0,p('SubstanceCompoundInfusion',SubstanceCompound='Blood',BagVolume=s('Volume',100,'mL'),Rate=s('VolumePerTime',10,'mL/min')))],
'probe_bvm':[(0,{'EquipmentAction':{'BagValveMaskConfiguration':{'Configuration':{'Connection':'On'}}}}),(0,{'EquipmentAction':{'BagValveMaskAutomated':{'BreathFrequency':s('Frequency',12,'1/min'),'InspiratoryExpiratoryRatio':{'Value':0.5},'SqueezeVolume':s('Volume',500,'mL')}}})],
}
if __name__=='__main__':
 import sys
 n.CASES.update(cases);n.run(sys.argv[1])
