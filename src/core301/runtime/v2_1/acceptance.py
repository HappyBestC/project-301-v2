import json,hashlib,math
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.exposure_validation import HALT_EVENTS
from .evidence import REFERENCES
CYCLE={'StartOfCardiacCycle','StartOfInhale','StartOfExhale'}
TARGET={'Hypoxia','Tachycardia'}
def reference(index,kind):
 item=REFERENCES[index][kind];p=PROJECT_ROOT/item['path']
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise V2Error('EVIDENCE_INVALID','Pinned composite reference missing/changed')
 return [json.loads(s) for s in p.read_text().splitlines()]
def numbered(rows):return {round(r['time_s']):r for r in rows if abs(r['time_s']-round(r['time_s']))<1e-6}
def repeat_check(actual,expected,end):
 a,b=numbered(actual),numbered(expected);missing=[n for n in range(end+1) if n not in a or n not in b];problems=[];maximum=0
 for n in set(a)&set(b):
  for group in ('values','diagnostics','events'):
   x,y=a[n][group],b[n][group]
   if set(x)!=set(y):problems.append(f'{n}:{group}:keys');continue
   for k in x:
    if x[k] is None or y[k] is None:
     if x[k]!=y[k]:problems.append(f'{n}:{group}:{k}:missing')
    elif not math.isfinite(x[k]) or not math.isfinite(y[k]):problems.append(f'{n}:{group}:{k}:nonfinite')
    else:maximum=max(maximum,abs(x[k]-y[k]))
 return {'passed':not missing and not problems and maximum<=1e-7,'precision':1e-7,'max_absolute_difference':maximum,'missing_seconds':missing,'problems':problems}
def evaluate(case):
 case._live();case._guard();end=case.pattern['simulation_timeline']['end_s'];decision=case.pattern['simulation_timeline']['decision_s']
 if abs(case._time()-end)>1e-6:raise V2Error('INCOMPLETE_WINDOW','Fixed endpoint not reached')
 rows=case._engine.rows;reference_rows=reference(case.index,'treated');control=reference(case.index,'control')
 repeat=repeat_check(rows,reference_rows,end);z=rows[-1];c=control[-1];d=z['diagnostics'];cd=c['diagnostics'];v=z['values'];cv=c['values'];i=case.index
 first={}
 for line in (case.directory/'native/native_events.jsonl').read_text().splitlines():
  r=json.loads(line)
  for e in r['events']:
   if e not in CYCLE:first.setdefault(e,r['time_s'])
 final=set(z['events'])-CYCLE
 resolved_targets={e for e,t in first.items() if e in TARGET and t<=decision and e not in final}
 unreviewed=set(first)-resolved_targets
 # No composite risk acceptance is present in this version.
 safety={'passed':not unreviewed and not final,'unreviewed_events':sorted(unreviewed),'final_events':sorted(final),'resolved_preexisting_target_events':sorted(resolved_targets),'critical_veto':bool(set(first)&HALT_EVENTS),'accepted_risk_exemptions':[]}
 if i==0:mechanisms={'A':v['laboratory.arterial_oxygen_pressure']>cv['laboratory.arterial_oxygen_pressure'],'B':'hemothorax' in case._controlled and d['residual_blood_volume_mL'] is not None and d['residual_blood_volume_mL']<cd['residual_blood_volume_mL']}
 elif i in (1,2):mechanisms={'A':d['diagnostic.TotalHemorrhageRate']==0 and d['diagnostic.TotalHemorrhagedVolume']<cd['diagnostic.TotalHemorrhagedVolume'] and d['diagnostic.BloodVolume']>cd['diagnostic.BloodVolume'],'B':d['left_pleural_volume_mL']<cd['left_pleural_volume_mL'] and v['laboratory.arterial_oxygen_pressure']>cv['laboratory.arterial_oxygen_pressure'] if i==1 else v['respiratory.tidal_volume']>cv['respiratory.tidal_volume'] and v['laboratory.arterial_carbon_dioxide_pressure']<cv['laboratory.arterial_carbon_dioxide_pressure']}
 elif i==3:
  initial=numbered(rows)[decision]['diagnostics'];mechanisms={'A':d['ambient_co_fraction']==0 and d['aorta_co_saturation']<initial['aorta_co_saturation'],'B':v['laboratory.arterial_oxygen_pressure']>cv['laboratory.arterial_oxygen_pressure']}
 else:mechanisms={'A':d['ambient_oxygen_fraction']==.21 and 'Hypoxia' not in final and v['laboratory.arterial_oxygen_pressure']>cv['laboratory.arterial_oxygen_pressure'],'B':d['total_fluid_mL']>cd['total_fluid_mL'] and d['diagnostic.BloodVolume']>cd['diagnostic.BloodVolume']}
 plans=list(case.journal['requests'].values());executed=any(p['state']=='COMPLETED' and p['plan']['bundle']=='AB' for p in plans)
 passed=repeat['passed'] and safety['passed'] and all(mechanisms.values()) and executed
 result={'pattern_id':case.pattern['pattern_id'],'version':'301.v2_1.acceptance.1','mechanisms':mechanisms,'safety':safety,'repeat':repeat,'execution_confirmed':executed,'engineering_case_passed':passed,'formal_admission':'NOT_GRANTED_BY_CASE_RESULT','validation_only':case.validation_only,'production_enabled':False,'clinical_safety':'NOT_EVALUATED'}
 (case.directory/'accepted_endpoint_state.json').write_text(case._engine.session.serialize_state());(case.directory/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n');return result
