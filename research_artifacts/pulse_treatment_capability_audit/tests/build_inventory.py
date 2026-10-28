import re,json,csv,importlib,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SRC=Path('/home/private/project-301/engine-stable/src');BIN=Path('/home/private/project-301/pulse/bin');PYROOT=Path('/home/private/project-301/pulse/python')
def writecsv(name,rows):
 with (ROOT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def loc(p,needle):
 s=p.read_text();i=s.find(needle);return str(p)+':'+str(s[:i].count('\n')+1 if i>=0 else 1)
def function(s,key):
 m=re.search(r'bool \w+::'+key+r'\(\) const\s*\{',s)
 if not m:return '见基类或模型配置处理；尚未逐项原生验证'
 i=m.end();depth=1;j=i
 while j<len(s) and depth:
  depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return re.sub(r'\s+',' ',s[i:j-1]).strip()
units={}
for p in (SRC/'cpp/cdm/properties').glob('SEScalar*.cpp'):
 vals=re.findall(r'const \w+Unit \w+Unit::\w+\("([^"]+)"\)',p.read_text());
 if vals:units[p.stem[2:]]=vals
(ROOT/'scalar_units.json').write_text(json.dumps(units,indent=2))
# Expand descriptor paths including nested equipment configuration, enums, oneof semantics.
def fields(d,prefix='',seen=()):
 out=[]
 if d.full_name in seen:return out
 for f in d.fields:
  name=prefix+f.name;extra=(' repeated' if f.label==3 else '')+(' oneof='+f.containing_oneof.name if f.containing_oneof else '')
  if f.enum_type:out.append(name+': enum{'+','.join(v.name+'='+str(v.number) for v in f.enum_type.values)+'}'+extra)
  elif f.message_type:
   n=f.message_type.name
   if n.startswith('Scalar'):
    base=n.removesuffix('Data');rng='[0,1]' if '0To1' in n else '[-1,1]' if 'Negative1To1' in n else 'double;非临床范围校验'
    out.append(name+': '+n+' '+rng+' units='+','.join(units.get(base,[]))+extra)
   else:
    out.append(name+': '+n+extra);out+=fields(f.message_type,name+'.',seen+(d.full_name,))
  else:out.append(name+': '+{1:'double',2:'float',5:'int32',8:'bool',9:'string',14:'enum'}.get(f.type,str(f.type))+extra)
 return out
modules=['PatientActions','EnvironmentActions','BagValveMaskActions','MechanicalVentilatorActions','ECMOActions','InhalerActions','AnesthesiaMachineActions']
therapies={'ChestOcclusiveDressing':'胸腔封闭敷料','NeedleDecompression':'针刺减压','TubeThoracostomy':'胸管引流','Intubation':'气道置管及口/鼻咽通气道','SupplementalOxygen':'氧疗','MechanicalVentilation':'通用机械通气','SubstanceBolus':'药物推注','SubstanceInfusion':'单物质静脉输注','SubstanceCompoundInfusion':'复合液/血液输注','ChestCompression':'单次胸外按压','ChestCompressionAutomated':'自动胸外按压','ChestCompressionInstantaneous':'即时胸外按压','ConsumeNutrients':'营养及口服补水','ConsciousRespiration':'指令呼吸/吸入器触发','RespiratoryMechanicsConfiguration':'呼吸力学配置','RespiratoryMechanicsModification':'呼吸力学修改','CardiovascularMechanicsModification':'心血管力学修改','ThermalApplication':'加热/冷却/体表温度控制','ChangeEnvironmentalConditions':'环境调整'}
rows=[];details={}
for mod in modules:
 md=importlib.import_module('pulse.cdm.bind.'+mod+'_pb2').DESCRIPTOR
 for name,d in md.message_types_by_name.items():
  n=name.removesuffix('Data');cpp=list((SRC/'cpp/cdm').rglob('SE'+n+'.cpp'))
  if not cpp or n.endswith('Action') or n in ['ForcedInhale','ForcedExhale','ForcedPause','UseInhaler','ConsciousRespirationCommand']:continue
  p=cpp[0];s=p.read_text();params=fields(d);details[n]=params
  matches=[]
  for py in (PYROOT/'pulse/cdm').glob('*actions.py'):
   if re.search(r'^class SE'+n+r'\(',py.read_text(),re.M):matches.append('pulse.cdm.'+py.stem+'.SE'+n)
  support='原生支持（S1，未验证项不推定运行成功）'
  if mod=='PatientActions' and n not in therapies:support='原生伤情/状态Action；作为治疗仅间接模拟'
  if any(x in n for x in ['Failure','Leak','Obstruction','Loss','Disconnect']):support='原生设备故障模拟；非治疗'
  life='持续/状态更新；具体有效性见IsActive；设备配置可能消费后留在设备状态'
  stop='同键覆盖；失活条件见IsActive；配置需反向配置，非通用撤销'
  grain='具名参数(double+单位/枚举)，按引擎时间步推进'
  if n in ['ChestOcclusiveDressing','NeedleDecompression']:grain='左右侧各一开关';stop='同侧State=Off';life='持续开关'
  if n=='Intubation':grain='单个Type槽位，可调Severity和AirwayResistance';stop='Type=Off'
  if n=='SubstanceBolus':grain='每物质：浓度×体积，途径、时长';stop='完成自然移除；同物质覆盖会重置进度；零Dose停剩余输入';life='有限时段注入，默认2s'
  if n=='SubstanceInfusion':grain='每物质：浓度、体积速率、剩余Volume';stop='Rate=0/浓度=0/Volume=0；袋耗尽；覆盖';life='持续，缺Volume默认1000mL'
  if n=='SubstanceCompoundInfusion':grain='每复合液：BagVolume、Rate；组分浓度由文件';stop='Rate=0或BagVolume=0；袋耗尽';life='持续'
  if n=='SupplementalOxygen':grain='设备枚举、流量、氧气总量';stop='Device=None；耗尽';life='持续设备状态'
  if n=='TubeThoracostomy':grain='侧别+FlowRate；源码IsActive要求有FlowRate';stop='同侧提交不含FlowRate使失活；零流量仍可能活跃，须谨慎';life='持续'
  if n=='Hemorrhage':grain='Compartment槽位+Type+Severity或FlowRate；不是血管/伤口';stop='同部位Severity=0或FlowRate=0（Severity优先）'
  rows.append(dict(treatment=therapies.get(n,n),action='SE'+n,support=support,python_interface=';'.join(matches) or '无同名高级Python类；PyPulse.Engine.process_actions(JSON, json) protobuf路径',parameters=' | '.join(params),required_validation=function(s,'IsValid'),active_validation=function(s,'IsActive'),granularity=grain,lifecycle=life,stop=stop,evidence='S1 '+loc(p,'::IsValid')+'; '+loc(SRC/'schema/pulse/cdm/bind'/ (mod+'.proto'),'message '+name),native_status='尚未验证（实验覆盖项见REPORT和tests）'))
for title in ['止血带','直接压迫/加压包扎/伤口填塞','手术缝合/血管结扎','骨折固定','电除颤','抗生素杀菌/感染控制','血型配型/输血反应']:
 rows.append(dict(treatment=title,action='无直接原生Action',support='当前版本不支持直接Action；止血可间接调SEHemorrhage',python_interface='',parameters='',required_validation='',active_validation='',granularity='无器材/操作细节',lifecycle='',stop='',evidence='S1 本地AnyPatientActionData及AnyEquipmentActionData枚举、CDM类全量扫描',native_status='未执行；不得等同临床模型'))
writecsv('action_inventory.csv',rows);(ROOT/'action_parameter_details.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
drugs=[]
for p in sorted((BIN/'substances').glob('*.json')):
 d=json.loads(p.read_text());pd=d.get('Pharmacodynamics',{});pk=d.get('Pharmacokinetics',{})
 drugs.append(dict(name=d.get('Name',p.stem),kind='物质（并非全部是药品）',state=d.get('State',''),PK=bool(pk),PD=bool(pd),clearance=bool(d.get('Clearance')),pd_fields=json.dumps(pd,ensure_ascii=False),routes='Bolus:IV/IA/IM（S1）；Infusion:IV；气体/气溶胶需相应设备，不能对所有物质保证途径合理',dose='Bolus质量=Concentration×Dose(体积); Infusion质量速率=Concentration×Rate; Volume可限总量',evidence=str(p)+':1',status='Epinephrine/Morphine见原生实验；其余仅S1；有PD也不等于完整或临床验证的模型' if pd else '无通用PD；可能有气体/电解质等专用生理机制，不能称无任何生理效果'))
for p in sorted((BIN/'substances/compounds').glob('*.json')):
 d=json.loads(p.read_text());drugs.append(dict(name=d.get('Name',p.stem),kind='Compound',state='',PK='',PD='',clearance='',pd_fields=json.dumps(d),routes='SESubstanceCompoundInfusion 静脉',dose='BagVolume+Rate；组分浓度来自文件',evidence=str(p)+':1',status='Saline见原生实验；其余S1尚未验证'))
writecsv('drug_inventory.csv',drugs)
import PyPulse
state=BIN/'states/Soldier@0s.json'
env=dict(version=PyPulse.__version__,module=PyPulse.__file__,module_sha256=hashlib.sha256(Path(PyPulse.__file__).read_bytes()).hexdigest(),patient_state=str(state),patient_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),source_version='/home/private/project-301/engine-stable/CMakeLists.txt:46',actions=len(rows),substances=len(drugs))
(ROOT/'environment.json').write_text(json.dumps(env,indent=2));print(env)
