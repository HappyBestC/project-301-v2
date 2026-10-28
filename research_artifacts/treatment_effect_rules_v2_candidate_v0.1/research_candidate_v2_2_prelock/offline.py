"""V2.2 offline layered interpreter. No simulator, approval writer or grade emitter."""
import copy,json,math,statistics,hashlib,datetime,sys
from pathlib import Path
D=Path(__file__).resolve().parent;C=D.parent;R=C.parents[1];OLD=C/'final_lock_and_validation_v0.1';H=C/'medical_review_handoff_v0.1'
sys.path.insert(0,str(OLD));from candidate_eval import Refusal,evaluate as old_evaluate,binary,finite

def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def reject(s):raise Refusal(s)
def config():return j(D/'RULE_TABLE_V2_2_DRAFT.json')
def value(cfg,k):
 if k not in cfg['parameter_registry']:reject('UNKNOWN_PARAMETER:'+k)
 x=cfg['parameter_registry'][k]['value']
 if x is None:reject('THRESHOLD_UNDETERMINED:'+k)
 return x

def eval_node(node,ctx,cfg):
 if isinstance(node,bool):return node
 if not isinstance(node,dict):reject('UNREFERENCED_LITERAL')
 if 'parameter' in node:return value(cfg,node['parameter'])
 if 'fact' in node:return old_evaluate(node,ctx,{},cfg)
 if 'data' in node:return old_evaluate(node,ctx,{},cfg)
 name=node['op'];args=node['args']
 if name=='if':return eval_node(args[1] if eval_node(args[0],ctx,cfg) else args[2],ctx,cfg)
 a=[eval_node(x,ctx,cfg) for x in args]
 if name in ['and','or']:
  def fn(x,y):
   if type(x) is not bool or type(y) is not bool:reject('BOOLEAN_TYPE_REQUIRED')
   return x and y if name=='and' else x or y
  z=a[0]
  for x in a[1:]:z=binary(fn,z,x)
  return z
 if name=='all':
  if not isinstance(a[0],list) or not a[0] or not all(type(x)is bool for x in a[0]):reject('NONEMPTY_BOOLEAN_SERIES_REQUIRED')
  return all(a[0])
 if name=='mean':return statistics.mean(a[0])
 if name=='first':return a[0][0]
 if name=='finite':return all(finite(x) for x in (a[0] if isinstance(a[0],list) else [a[0]]))
 if name=='abs':return [abs(x) for x in a[0]] if isinstance(a[0],list) else abs(a[0])
 if name in ['distance','between']:
  x,rg=a
  if not isinstance(rg,list) or len(rg)!=2 or not all(finite(v) for v in rg) or rg[0]>rg[1]:reject('INVALID_REFERENCE_INTERVAL')
  fn=(lambda v:max(rg[0]-v,0,v-rg[1])) if name=='distance' else (lambda v:rg[0]<=v<=rg[1])
  return [fn(v) for v in x] if isinstance(x,list) else fn(x)
 def div(x,y):
  if not finite(y) or y<=0:reject('INVALID_DENOMINATOR_OR_MODE_UNDEFINED')
  return x/y
 funcs={'sub':lambda x,y:x-y,'mul':lambda x,y:x*y,'div':div,'ge':lambda x,y:x>=y,'gt':lambda x,y:x>y,'le':lambda x,y:x<=y,'lt':lambda x,y:x<y,'eq':lambda x,y:x==y}
 if name not in funcs:reject('UNKNOWN_OPERATOR:'+name)
 return binary(funcs[name],*a)

def validate_ast(cfg):
 used=set()
 def walk(n):
  if isinstance(n,bool):return
  if not isinstance(n,dict):reject('AST_NUMERIC_LITERAL_OR_INVALID_NODE')
  if 'parameter' in n:
   if n['parameter'] not in cfg['parameter_registry']:reject('UNKNOWN_PARAMETER:'+n['parameter'])
   used.add(n['parameter']);return
  if 'fact' in n:return
  if 'data' in n:
   if n['data'] not in cfg['metrics']:reject('UNKNOWN_METRIC')
   return
  if n.get('op') not in ['and','or','if','all','mean','first','finite','abs','distance','between','sub','mul','div','ge','gt','le','lt','eq']:reject('UNKNOWN_OPERATOR')
  for x in n['args']:walk(x)
 for r in cfg['rules']:
  for n in r['variant_A']['definitions'].values():walk(n)
  for layer in r['variant_B']['layers'].values():
   for n in layer.get('expressions',{}).values():walk(n)
 for p in cfg['profile_safety'].values():
  for n in p['predicates'].values():walk(n)
 return used

def validate_time(ctx,cfg):
 for k in ['baseline_time_s','query_time_s','available_at_s']:
  if not finite(ctx.get(k)):reject('TIME_MISSING:'+k)
 if not ctx['baseline_time_s']<ctx['query_time_s']<=ctx['available_at_s']:reject('FUTURE_OR_INVALID_QUERY')
 tol=value(cfg,'sampling.clock_tolerance_s');win=value(cfg,'window.tail_s')
 for w,ts in ctx.get('times',{}).items():
  if not ts or not all(finite(x) for x in ts):reject('TIME_MISSING:'+w)
  if any(y<=x for x,y in zip(ts,ts[1:])):reject('DUPLICATE_OR_REVERSED_FRAME:'+w)
  if ts[-1]>ctx['query_time_s']:reject('FUTURE_FRAME:'+w)
  if ts[0]<=ctx['baseline_time_s']:reject('BASELINE_IN_POST_WINDOW:'+w)
  step=value(cfg,'sampling.pleural_step_s' if w=='H' else 'sampling.public_step_s')
  if w!='POST' and any(abs(y-x-step)>tol for x,y in zip(ts,ts[1:])):reject('GAP_OR_WRONG_GRID:'+w)
  if w=='POST' and any(y-x>step+tol for x,y in zip(ts,ts[1:])):reject('POST_GAP')
  if w in ['W','H'] and (abs(ts[-1]-ctx['query_time_s'])>tol or abs(ts[0]-(ctx['query_time_s']-win))>tol):reject('WRONG_WINDOW:'+w)
 if ctx['times'].get('C')!=ctx['times'].get('W'):reject('CONTROL_WINDOW_MISMATCH')
 if not ctx.get('pairing',{}).get('verified'):reject('CONTROL_PAIR_NOT_VERIFIED')
 if not ctx['pairing'].get('shared_baseline'):reject('CONTROL_BASELINE_MISMATCH')
 if ctx['pairing']['rule_id']!=ctx['rule_id'] or ctx['pairing']['case_id']!=ctx['case_id']:reject('CONTROL_PROFILE_MISMATCH')


def patient_PBW(path,expected_hash):
 p=R/path
 if sha(p)!=expected_hash:reject('PATIENT_HASH_MISMATCH')
 obj=j(p);pt=obj.get('InitialPatient',obj);height=pt['Height']['ScalarLength'];u=height['Unit'];h=height['Value']
 if u=='cm':h/=2.54
 elif u=='m':h*=100/2.54
 elif u!='in':reject('PATIENT_HEIGHT_UNIT')
 sex=pt.get('Sex','Male') # protobuf default sex enum omitted in pinned states
 if sex not in ['Male','Female']:reject('PATIENT_SEX_UNKNOWN')
 kg=(45.5 if sex=='Female' else 50)+2.3*(h-60)
 if not finite(kg) or kg<=0:reject('INVALID_PBW')
 stored=pt.get('IdealBodyWeight',{}).get('ScalarMass')
 if stored and (stored.get('Unit')!='kg' or abs(stored.get('Value',0)-kg)>1e-6):reject('PATIENT_IBW_FORMULA_CONFLICT')
 return kg

def reference_check(ctx,cfg):
 e=ctx['healthy_reference']
 if not e.get('research_read_authorized'):reject('REFERENCE_UNAUTHORIZED')
 if e['role']!='RETROSPECTIVE_CALIBRATION_REFERENCE_NOT_PATIENT_EVENT' or ctx.get('use_mode')!='RETROSPECTIVE_RESEARCH':reject('REFERENCE_NOT_AVAILABLE_FOR_HISTORICAL_ONLINE_QUERY')
 if datetime.datetime.fromisoformat(e['available_by_review_utc'])>datetime.datetime.fromisoformat(ctx['review_as_of_utc']):reject('FUTURE_REFERENCE_AVAILABILITY')
 for k,h in [('source','source_sha256'),('raw','raw_sha256'),('patient_state','patient_state_sha256'),('plan','plan_sha256'),('initial_state','initial_state_sha256'),('preflight','preflight_sha256')]:
  if sha(R/e[k])!=e[h]:reject('REFERENCE_HASH_MISMATCH:'+k)
 rf=j(R/e['source']);plan=j(R/e['plan']);state=j(R/e['patient_state']);initial=j(R/e['initial_state']);other=j(R/ctx['matched_patient_source'])
 if e['engine']!='4.3.2' or not other['Version'].startswith(e['engine']) or not initial['Version'].startswith(e['engine']):reject('REFERENCE_ENGINE_MISMATCH')
 if state['InitialPatient']!=other['InitialPatient'] or state['InitialPatient']!=initial['InitialPatient']:reject('REFERENCE_PATIENT_MISMATCH')
 def env(s):return {k:v for k,v in s['Environment']['Common']['EnvironmentalConditions'].items() if k!='AirDensity'}
 if env(state)!=env(other) or env(state)!=env(initial):reject('REFERENCE_ENVIRONMENT_MISMATCH')
 if e['padding_applications']!=1 or rf['padding_applications']!=1:reject('REFERENCE_DOUBLE_PADDING')
 if e['observed_simulation_window_s']!=[rf['sampling']['selected_start_s'],rf['sampling']['selected_end_exclusive_s']]:reject('REFERENCE_TIME_MISMATCH')
 if value(cfg,'reference.pressure_final_range')!=rf['pressure']['padded_range'] or value(cfg,'reference.volume_final_range')!=rf['volume']['padded_range']:reject('REFERENCE_RANGE_TAMPER_OR_DOUBLE_PADDING')
 if not rf['technical_quality_pass'] or rf['pathological_or_stabilizing_events_full300s']:reject('REFERENCE_QUALITY_FAILED')
 if e['applicability_approval']!='PENDING' or e['medical_approval']!='PENDING':reject('UNSUPPORTED_REFERENCE_APPROVAL_CLAIM')
 return {'provenance':'VERIFIED','technical_quality':'PASS','applicability_approval':'PENDING','medical_approval':'PENDING','role':e['role'],'source_sha256':e['source_sha256'],'available_by_review_utc':e['available_by_review_utc'],'observed_simulation_window_s':e['observed_simulation_window_s'],'padding_applications':1}

_cached=None

def load_case(case_id,cfg=None):
 global _cached
 cfg=cfg or config()
 if _cached is None:
  pins=j(D/'INPUT_SHA256.json')
  for p,h in pins.items():
   if sha(R/p)!=h:reject('INPUT_HASH_MISMATCH:'+p)
  _cached=j(H/'COMPUTED_EVIDENCE.json')['cases']
 rec=copy.deepcopy(next(x for x in _cached if x['case']==case_id));ctx=copy.deepcopy(rec['context']);rid=rec['rule_id'];ctx.update(case_id=case_id,rule_id=rid,use_mode='RETROSPECTIVE_RESEARCH',review_as_of_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pairing={'verified':True,'rule_id':rid,'case_id':case_id,'basis':'pinned original adapter replay and native SHA chain','shared_baseline':rec['treatment'][0]['values']==rec['control'][0]['values']})
 if not ctx['pairing']['shared_baseline']:reject('CONTROL_BASELINE_MISMATCH')
 ctx['POST']['elapsed_s']=[t-ctx['baseline_time_s'] for t in ctx['times']['POST']];ctx['units']['elapsed_s']='s';ctx['patient_source']=None
 if rid=='V2E-10':
  path='research_artifacts/v2_engineering_phase1/validation/native_cases_final/fatigue/pretreatment_state.json';h=sha(R/path);ctx['patient_source']=path
  ctx['facts']['patient_PBW_kg']={'value':patient_PBW(path,h),'source':path,'source_sha256':h,'observed_at_s':ctx['baseline_time_s'],'available_at_s':ctx['baseline_time_s'],'authorized':True}
 if rid in ['V2E-07','V2E-08']:
  ctx['healthy_reference']=j(D/'HEALTHY_REFERENCE_ENVELOPE.json');ctx['matched_patient_source']='research_artifacts/v2_engineering_phase1/validation/native_cases_final/'+('open_left' if rid=='V2E-07' else 'closed_left')+'/pretreatment_state.json'
 rec['runtime_context']=ctx
 return rec

def safety(ctx,profile,cfg,original):
 events=copy.deepcopy(original['native_events_retained']);critical=set(original['confirmed_critical_events'])|set(ctx.get('additional_confirmed_native_events',[]));critical &= set(profile['critical_events']);scans={};missing=[]
 for metric,node in profile['predicates'].items():
  required=cfg['metrics'][metric]['source_key'] in {x['key'] for x in profile['required_fields']};base=ctx.get('B',{}).get(metric);post=ctx.get('POST',{}).get(metric,[]);ts=ctx['times']['POST']
  try:
   hits=eval_node(node,ctx,cfg);assert isinstance(hits,list);trigger=[{'time_s':t,'value':v} for t,v,h in zip(ts,post,hits) if h]
   # Re-evaluate the same policy at B with elapsed zero; no duplicated thresholds.
   bc=copy.deepcopy(ctx);bc['POST']={k:[v] for k,v in ctx['B'].items()};bc['POST']['elapsed_s']=[0];bc['times']['POST']=[ctx['baseline_time_s']];atB=eval_node(node,bc,cfg)[0]
   scans[metric]={'required':required,'baseline':base,'baseline_trigger':atB,'endpoint':post[-1],'endpoint_delta':post[-1]-base,'post_min':min(post),'post_max':max(post),'trigger_count':sum(hits),'trigger_samples':trigger,'missing_count':0,'baseline_event_or_numeric_abnormal_persists':bool(atB and hits[-1]),'new_numeric_trigger':bool(not atB and any(hits)),'last_trigger':bool(hits[-1]),'trend_is_numeric_not_medical_benefit':True}
  except (Refusal,KeyError,TypeError,ValueError,AssertionError) as e:
   scans[metric]={'required':required,'status':'UNAVAILABLE','reason':str(e),'baseline':base,'missing_count':sum(v is None for v in post) if post else len(ts)}
   if required:missing.append(metric)
 return {'state':'VETO' if critical else 'UNRESOLVED','confirmed_critical_events':sorted(critical),'metric_review':scans,'required_missing':missing,'native_events':events,'profile_approval':profile['approval'],'reason':'CRITICAL_NATIVE_EVENT' if critical else 'PROFILE_MEDICAL_OWNER_EVENT_POLICY_PENDING','no_clinical_safety_claim':True}

def calculate(case,variant='B',cfg=None):
 cfg=copy.deepcopy(cfg or config());rec=copy.deepcopy(case);ctx=rec['runtime_context'];rid=rec['rule_id'];r=next(x for x in cfg['rules'] if x['rule_id']==rid);profile=cfg['profile_safety'][rid+'/'+rec['case']]
 for original_key,new_key in profile['parameter_overrides'].items():
  if original_key not in cfg['parameter_registry'] or new_key not in cfg['parameter_registry']:reject('INVALID_PROFILE_PARAMETER_OVERRIDE')
  cfg['parameter_registry'][original_key]=copy.deepcopy(cfg['parameter_registry'][new_key])
 out={'rule_id':rid,'case':rec['case'],'variant':variant,'version':cfg['version'],'parameter_sha256':digest(cfg['parameter_registry']),'configuration_sha256':digest(cfg),'status':cfg['status'],'execution':{},'mechanism':{},'physiological_response':{},'safety':safety(ctx,profile,cfg,rec['replay']['safety']),'evidence_quality':{'errors':[],'source_sha256':rec['replay']['source_sha256']},'candidate_grade':{'status':'APPROVAL_PENDING','value':None,'enabled':False,'blockers':['OWNER_APPROVAL_PENDING','MEDICAL_SAFETY_PENDING','EVENT_POLICY_PENDING','INDEPENDENT_VALIDATION_NOT_RUN','FORMAL_SCORING_DISABLED']},'formal_label_generated':False}
 errors=out['evidence_quality']['errors'];refok=True
 try:
  validate_ast(cfg);validate_time(ctx,cfg)
  if ctx['rule_id']!=rid or ctx['case_id']!=rec['case'] or not ctx['pairing']['shared_baseline']:reject('CASE_IDENTITY_OR_BASELINE_MISMATCH')
  if rid=='V2E-10':
   p=ctx['patient_source'];h=j(D/'INPUT_SHA256.json').get(p)
   if not h or p!='research_artifacts/v2_engineering_phase1/validation/native_cases_final/fatigue/pretreatment_state.json':reject('PATIENT_OUTSIDE_FIXED_PROFILE')
   if ctx['facts']['patient_PBW_kg']['value']!=patient_PBW(p,h):reject('PBW_VALUE_MISMATCH')
  if digest(ctx.get('C'))!=digest(rec['context'].get('C')):reject('CONTROL_VALUES_NOT_MATCHED_TO_ARCHIVE')
  if digest(ctx.get('B'))!=digest(rec['context'].get('B')):reject('BASELINE_VALUES_NOT_MATCHED_TO_ARCHIVE')
  accepted=eval_node(r['variant_A']['definitions']['prerequisites'],ctx,cfg);out['execution']={'prerequisites':accepted,'receipt_evidence':rec['replay'].get('execution_evidence',{}),'accepted_is_not_mechanism':True}
  if accepted is not True:reject('EXECUTION_OR_SCOPE_PREREQUISITE_NOT_MET')
 except (Refusal,KeyError,TypeError,ValueError) as e:
  errors.append(str(e));out['candidate_grade']['status']='NOT_EVALUABLE';out['candidate_grade']['blockers']+=errors;return out
 if rid in ['V2E-07','V2E-08']:
  try:out['evidence_quality']['healthy_reference']=reference_check(ctx,cfg)
  except (Refusal,KeyError,TypeError,ValueError) as e:errors.append(str(e));refok=False
 def ev(node):
  if not refok and ('reference.' in json.dumps(node)):return {'value':None,'status':'REFERENCE_UNAVAILABLE','reason':errors[-1]}
  try:
   result=eval_node(node,ctx,cfg);return {'value':result,'status':'COMPUTED','reason':'CONDITION_NOT_MET' if result is False else None}
  except (Refusal,KeyError,TypeError,ValueError) as e:return {'value':None,'status':'NOT_EVALUABLE','reason':str(e)}
 if variant=='A':
  out['mechanism']['original_mechanism']=ev(r['variant_A']['definitions']['mechanism_minimum']);out['physiological_response']['original_target']={k:ev(r['variant_A']['definitions'][k]) for k in ['minimum','complete']}
 elif variant=='B':
  for name,layer in r['variant_B']['layers'].items():
   kind=layer['kind']
   if kind=='expressions':res={k:ev(node) for k,node in layer['expressions'].items()}
   elif kind=='evidence_fact':
    res=ev({'fact':layer['fact']})
    if res['value'] is None:res['status']=layer['missing_status']
   elif kind=='unresolved':res={'value':None,'status':'APPROVAL_PENDING','reason':layer['reason']}
   elif kind=='metric_change':
    res={}
    for k in layer['metrics']:
     node=op_mean_delta(k,'C' if layer['comparison']=='MATCHED_CONTROL' else 'B');res[k]={'self_mean_change':ev(op_mean_delta(k,'B')),'control_mean_difference':ev(op_mean_delta(k,'C')),'unit':'pp' if k=='SpO2' else cfg['metrics'][k]['unit']}
   else:reject('UNKNOWN_LAYER_KIND')
   (out['mechanism'] if name in ['direct_mechanism','blood_control','dehydration_deficit','local_mechanism','recurrence'] else out['physiological_response'])[name]=res
  if r['variant_B']['candidate_grade']['status']=='THRESHOLD_UNDETERMINED':out['candidate_grade']['status']='THRESHOLD_UNDETERMINED';out['candidate_grade']['blockers']+=['OVERALL_TARGET_AGGREGATION_UNDEFINED']+r['open_parameters']
 else:reject('UNKNOWN_VARIANT')
 # Independent descriptive self and Control response, all retained even when a layer is undefined.
 for k in r['physiological_reporting']['metrics']:
  out['physiological_response'].setdefault('observed_changes',{})[k]={'self':ev(op_mean_delta(k,'B')),'vs_control':ev(op_mean_delta(k,'C')),'unit':'pp' if k=='SpO2' else cfg['metrics'][k]['unit']}
 if rid in ['V2E-07','V2E-08']:
  out['candidate_grade']['blockers'].append('REFERENCE_APPLICABILITY_APPROVAL_PENDING')
  if (D/'MECHANISM_SNAPSHOT_INDEX.json').exists():out['mechanism']['supplemental_endpoint_states']=[x for x in j(D/'MECHANISM_SNAPSHOT_INDEX.json')['records'] if x['rule_id']==rid and x['simulation_time_s']<=ctx['query_time_s']]

 if rid in ['V2E-02','V2E-03','V2E-05','V2E-06']:out['candidate_grade']['blockers'].append('MAP_TARGET_CHANGE_APPROVAL_PENDING')
 if out['safety']['state']=='VETO':out['candidate_grade']['blockers'].append('CRITICAL_NATIVE_EVENT_RETAINED')
 # Collect specific layer failures without converting missing evidence into false.
 def missing(o,path=''):
  if isinstance(o,dict):
   if o.get('status') in ['NOT_EVALUABLE','REFERENCE_UNAVAILABLE','MECHANISM_EVIDENCE_INSUFFICIENT','APPROVAL_PENDING']:yield {'layer':path,'reason':o.get('reason')}
   for k,x in o.items():yield from missing(x,path+'/'+k)
 out['evidence_quality']['layer_unavailability']=list(missing({'mechanism':out['mechanism'],'physiological':out['physiological_response']}))
 out['candidate_grade']['blockers']+=errors
 return out

def op_mean_delta(k,window):
 n={'op':'sub','args':[{'data':k,'window':'W'},{'data':k,'window':window}]}
 if k=='SpO2':n={'op':'mul','args':[{'parameter':'unit.fraction_to_percent'},n]}
 return {'op':'mean','args':[n]}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--case');p.add_argument('--variant',choices=['A','B'],default='B');p.add_argument('--output',default='REPLAY_V2_2.json');args=p.parse_args();cfg=config();names=[args.case] if args.case else [x['case'] for x in j(H/'COMPUTED_EVIDENCE.json')['cases']];results=[calculate(load_case(n,cfg),args.variant,cfg) for n in names]
 dest=(D/args.output).resolve()
 if dest.parent!=D:reject('OUTPUT_OUTSIDE_CANDIDATE_DIR')
 dest.write_text(json.dumps({'variant':args.variant,'cases':results,'new_native_runs':0,'formal_labels':0,'config_file_sha256':sha(D/'RULE_TABLE_V2_2_DRAFT.json')},ensure_ascii=False,indent=2,allow_nan=False)+'\n');print('replayed',len(results),'cases',args.variant)
