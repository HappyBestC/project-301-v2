import json,csv,math,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent.parent;raw=R/'tests/raw';checks=[]
def check(cond,label):
 assert cond,label
 checks.append(label)
def load(case,file):return json.loads((raw/case/file).read_text())
def actions(case,file):return load(case,file).get('ActiveActions',{}).get('AnyAction',[])
for case in ['airway_AB','airway_BA']:
 ev=load(case,'events.json');check([e['accepted'] for e in ev if 'accepted'in e]==[True,True],case+' submitted true');check(any('advance_failed_at_step' in e for e in ev),case+' failed step retained');check(ev[-1]['final_time_s']==0,case+' did not advance')
check(len(actions('combo_high_AB','submit_0_1.json'))==2,'two compatible actions retained at t=0')
check(not actions('infusion_update_stop','final.json'),'infusion stopped')
check(len(actions('overlap','submit_1000_0.json'))==2,'persistent overlap at 20s')
check(len(actions('overlap','final.json'))==1,'saline remains after oxygen stopped')
check(not actions('unsupported_route','final.json'),'unsupported IO route removed')
check(not actions('dressing_without_injury','final.json'),'dressing without injury removed')
check([e['accepted'] for e in load('invalid_missing_dose','events.json') if 'accepted'in e]==[False],'missing dose rejected')
b=load('batch_partial','events.json');check(b['accepted']==False and len(b['active_after_submit']['AnyAction'])==2 and b['advance_ok'],'failed batch partially applied')
check(len(actions('probe_tube','submit_0_0.json'))==0,'tube without FlowRate accepted but inactive')
for name in ['combo_high_AB vs combo_high_BA','epi_high vs bolus_overwrite']:
 check(json.loads((R/'comparison_checks.json').read_text())[name]['max_abs_difference_all_recorded_finite_columns']==0,name)
for f in ['REPORT.md','action_inventory.csv','drug_inventory.csv','conflict_matrix.csv','SOURCE_EVIDENCE.md','physiology_comparison.csv']:
 check((R/f).stat().st_size>100,f+' exists')
for p in raw.glob('*/samples.csv'):
 rows=list(csv.DictReader(p.open()));check(abs(float(rows[0]['time_s']))<1e-12,p.parent.name+' starts at zero')
(R/'artifact_validation.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks},indent=2));print('Artifact checks passed:',len(checks))
