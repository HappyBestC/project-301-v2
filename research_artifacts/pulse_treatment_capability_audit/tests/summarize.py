import json,csv,math,re,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent.parent;raw=R/'tests/raw'
def csvwrite(p,rows):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary=[];data={}
for d in sorted(raw.iterdir()):
 if not (d/'samples.csv').exists():continue
 ev=json.loads((d/'events.json').read_text());rows=[{k:float(v) for k,v in x.items()} for x in csv.DictReader((d/'samples.csv').open())];data[d.name]=rows
 failures=[x for x in ev if 'exception'in x or 'advance_failed_at_step'in x]
 submits=[x for x in ev if 'accepted'in x]
 summary.append(dict(case=d.name,accepted=str([x['accepted'] for x in submits]),advance_status='失败' if failures else '成功',final_time_s=ev[-1].get('final_time_s',''),failure=json.dumps(failures),evidence=str(d.relative_to(R))))
csvwrite(R/'test_results.csv',summary)
comparisons=[]
for name in ['baseline','epi_low','epi_high','saline','combo_high_AB','combo_high_BA','morphine','multidrug_high','chest_control','chest_dressing','hemorrhage_control','hemorrhage_stop']:
 for t in [5,10,20,60]:
  row=min(data[name],key=lambda r:abs(r['time_s']-t));comparisons.append({'case':name,'requested_sample_s':t,**row})
csvwrite(R/'physiology_comparison.csv',comparisons)
checks={}
for a,b in [('combo_AB','combo_BA'),('combo_high_AB','combo_high_BA'),('epi_high','bolus_overwrite'),('baseline','unsupported_route'),('baseline','dressing_without_injury')]:
 # scheduled steps may add extra samples; compare common 5s-grid samples only
 diffs=[]
 for x in data[a]:
  match=[y for y in data[b] if abs(y['time_s']-x['time_s'])<1e-8]
  if match:
   for k,v in x.items():
    if math.isfinite(v) and math.isfinite(match[0][k]):diffs.append(abs(v-match[0][k]))
 checks[a+' vs '+b]={'max_abs_difference_all_recorded_finite_columns':max(diffs)}
(R/'comparison_checks.json').write_text(json.dumps(checks,indent=2))
# Inventory annotations retain all source validation details.
a=list(csv.DictReader((R/'action_inventory.csv').open()))
verified={'SESubstanceBolus':'S2/S3/S4 epi_low,epi_high,morphine；IA/IM仅1s运行S3；Intraosseous被接受但下一步移除无效', 'SESubstanceInfusion':'S2/S3 infusion_update_stop；本低速率未见明确S4', 'SESubstanceCompoundInfusion':'S2/S3/S4 saline；Blood仅1s S3', 'SESupplementalOxygen':'S2/S3 overlap；有SpO2变化但未单列氧疗析因S4', 'SEChestOcclusiveDressing':'S2/S3/S4 chest_dressing；无伤情时接受后移除', 'SEHemorrhage':'S2/S3/S4 hemorrhage_stop；止血仅间接', 'SEMechanicalVentilation':'S2/S3 probe_mv；与氧疗冲突推进失败', 'SEIntubation':'S2/S3 probe_intubation，未验证疗效', 'SENeedleDecompression':'S2/S3 probe_needle，未验证疗效', 'SETubeThoracostomy':'S2/S3 probe_tube，未验证引流疗效', 'SEBagValveMaskConfiguration':'S2/S3 probe_bvm，未验证疗效','SEBagValveMaskAutomated':'S2/S3 probe_bvm，未验证疗效'}
for row in a:
 row['native_status']=verified.get(row['action'],row['native_status'])
 row['input_note']='TotalInfusedDose/TotalBloodLost/TotalBloodVolume为引擎状态输出，非推荐输入；Comment为元数据；oneof互选；枚举0值省略不等于缺失'
 if row['action']=='SEMechanicalVentilatorMode':row['support']='基类/嵌套结构，非独立可提交Action'
 if row['action']=='SEPatientAssessmentRequest':row['support']='原生评估请求，非治疗'
 if row['action']=='SEUrinate':row['support']='原生排尿生理动作，非通用创伤治疗'
 if row['action']=='SEThermalApplication':row.update(lifecycle='持续；AppendToPrevious控制追加或替换',stop='对应功率设0/温度State=Off或新配置替换',granularity='功率、温度、面积/面积比例；无解剖部位')
 if row['action']=='SEConsciousRespiration':row.update(lifecycle='有序命令队列；各子动作可有呼吸时长',stop='队列完成；新命令行为见Copy；无通用回滚',granularity='ForcedInhale/Exhale/Pause/UseInhaler子命令')
 if 'MechanicsModification' in row['action']:row['lifecycle']='默认非Incremental可能触发重新稳态；不能保证仅存动作不推进模型'
csvwrite(R/'action_inventory.csv',a)
d=list(csv.DictReader((R/'drug_inventory.csv').open()))
for row in d:
 if row['name']=='Prednisone':row['status']='S1：虽有PD块，全部效应modifier为0；无专门抗炎机制证据；不得判为抗炎有效'
 if row['name']=='Naloxone':row['status']='S1：通用负镇静/正呼吸modifier；未见阿片受体竞争拮抗模型；未原生验证'
 if row['name'] in ['Epinephrine','Morphine']:row['status']='S2/S3/S4：见tests/raw及physiology_comparison.csv；Epinephrine有剂量对照，Morphine单剂量'
 if row['name']=='Saline':row['status']='S2/S3/S4：血容量对照'
 if row['name']=='Blood':row['status']='S2/S3：1秒原生运行；S4未验证'
csvwrite(R/'drug_inventory.csv',d)
# Focused matrix, unknown combinations remain explicit.
names=['SubstanceBolus','SubstanceInfusion','SubstanceCompoundInfusion','SupplementalOxygen','MechanicalVentilation','Intubation','ChestOcclusiveDressing','NeedleDecompression','TubeThoracostomy','Hemorrhage','BagValveMaskAutomated','MechanicalVentilatorPressureControl','MechanicalVentilatorVolumeControl','ChestCompression','ChestCompressionAutomated','ThermalApplication','ECMOConfiguration','InhalerConfiguration']
mx=[]
for i,x in enumerate(names):
 for y in names[i:]:
  st='未知';ev='尚未验证；无通用兼容性保证';rule='需按具体参数、伤情和设备状态验证';owner='Agent临床/资源/组合校验'
  if x==y:
   st='同键覆盖（配置类另有Merge/Append语义）';ev='S1 SEPatientActionCollection.cpp:193 / SEEquipmentActionCollection.cpp:121';rule='单例按类型；侧别按侧；物质/复合物按名称；Hemorrhage按Compartment'
   if x in ['SubstanceBolus','SubstanceInfusion','Intubation']:ev+='; S2/S3 '+ {'SubstanceBolus':'bolus_overwrite','SubstanceInfusion':'infusion_update_stop','Intubation':'probe_intubation'}[x]
  pair={x,y}
  if pair=={'SubstanceBolus','SubstanceCompoundInfusion'}:st='共存并共同影响';ev='S1 DrugModel.cpp:145; S2/S3/S4 combo_high_AB/BA';rule='同刻提交，零时间推进；本组合交换次序数值一致'
  if pair=={'SubstanceCompoundInfusion','SupplementalOxygen'}:st='持续重叠共存/独立停止';ev='S2/S3 overlap';rule='0s盐水，20s氧疗，40s停氧后盐水继续'
  if pair=={'SupplementalOxygen','MechanicalVentilation'}:st='互斥：提交接受，推进失败';ev='S1 Controller.cpp:88; S2/S3 airway_AB/BA';rule='必须关闭旧设备并推进确认Free后启用新设备'
  if pair=={'MechanicalVentilatorPressureControl','MechanicalVentilatorVolumeControl'}:st='模式替换';ev='S1 SEEquipmentActionCollection.cpp:160-230；尚未原生验证';rule='新模式移除旧模式；ToSettings还可能失败'
  if pair=={'ChestCompression','ChestCompressionAutomated'}:st='自动移除其他按压模式';ev='S1 SEPatientActionCollection.cpp:298；尚未原生验证';rule='新动作替换旧按压模式'
  if pair=={'ChestOcclusiveDressing','NeedleDecompression'}:st='同侧可并存（源码）';ev='S1 RespiratoryModel.cpp:1730；组合尚未原生验证';rule='作用不同阻力路径；需同侧气胸，不能推定所有伤情适用'
  if x!=y and x in ['SupplementalOxygen','MechanicalVentilation','BagValveMaskAutomated','MechanicalVentilatorPressureControl','MechanicalVentilatorVolumeControl'] and y in ['SupplementalOxygen','MechanicalVentilation','BagValveMaskAutomated','MechanicalVentilatorPressureControl','MechanicalVentilatorVolumeControl'] and st=='未知':
   st='气道模式互斥（源码推断）';ev='S1 Controller.cpp:88及设备SetAirwayMode；未原生验证该配对';rule='设备连接状态决定；不能只凭动作类判断'
  mx.append(dict(action_A=x,action_B=y,status=st,rule=rule,evidence=ev,responsibility=owner))
mx.extend([dict(action_A='SubstanceBolus(Epinephrine)',action_B='SubstanceBolus(Morphine)',status='异物质共存',rule='独立注入与通用PD叠加；不代表药物特异相互作用',evidence='S2/S3/S4 multidrug_high',responsibility='Agent药物交互风险审查'),dict(action_A='Saline+invalidBolus+Oxygen',action_B='单批次process_actions',status='部分执行，无原子回滚',rule='整体false但Saline和Oxygen保留且下一步成功',evidence='S1 PhysiologyEngineThunk.cpp:268; S2/S3 batch_partial',responsibility='Agent逐项回执与失败后状态核对')])
csvwrite(R/'conflict_matrix.csv',mx)
# Preserve selected source excerpts with original absolute paths and line numbers.
src=Path('/home/private/project-301/engine-stable/src')
selections={'cpp/cdm/PhysiologyEngineThunk.cpp':[(268,309)],'cpp/cdm/engine/SEActionManager.cpp':[(71,100)],'cpp/cdm/engine/SEPatientActionCollection.cpp':[(193,218),(298,385),(438,490),(584,670),(1436,1515)],'cpp/cdm/engine/SEEquipmentActionCollection.cpp':[(121,300)],'cpp/engine/common/controller/Controller.cpp':[(88,110),(583,633),(828,874)],'cpp/engine/common/system/physiology/DrugModel.cpp':[(145,173),(193,390),(515,640)],'cpp/engine/common/system/physiology/RespiratoryModel.cpp':[(1090,1190),(1730,1845),(1870,1940)],'cpp/cdm/substance/SESubstanceManager.cpp':[(271,335)]}
lines=['# 本地源码证据摘录（原始行号）'];hashes={}
for rel,ranges in selections.items():
 p=src/rel;s=p.read_text();hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();ls=s.splitlines();lines+=['\n## '+str(p)]
 for lo,hi in ranges:lines+=['```cpp']+[f'{j}: {ls[j-1]}' for j in range(lo,min(hi,len(ls))+1)]+['```']
(R/'SOURCE_EVIDENCE.md').write_text('\n'.join(lines));(R/'source_hashes.json').write_text(json.dumps(hashes,indent=2))
print('cases',len(summary),'matrix',len(mx),'checks',checks)
# Attach exact high-level Python method names for every available class.
import ast
lookup={}
for p in Path('/home/private/project-301/pulse/python/pulse/cdm').glob('*actions.py'):
 for c in ast.parse(p.read_text()).body:
  if isinstance(c,ast.ClassDef):lookup[c.name]=[m.name for m in c.body if isinstance(m,ast.FunctionDef) and not m.name.startswith('__')]
for x in a:
 x['python_methods']=';'.join(lookup.get(x['action'],[]))
 if x['action']=='SESubstanceCompoundInfusion':x['stop']='Rate=0立即失活；BagVolume耗尽/为0于模型步移除；同名覆盖'
csvwrite(R/'action_inventory.csv',a)
