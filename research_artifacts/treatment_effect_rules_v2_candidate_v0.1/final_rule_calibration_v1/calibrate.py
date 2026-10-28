"""Read-only archived evidence adapters and candidate subcondition evaluation. No grades or Pulse."""
import sys,json,copy,math,statistics,datetime
from pathlib import Path
D=Path(__file__).resolve().parent;C=D.parent;R=C.parents[1];V=C/'research_candidate_v2_2_prelock'
sys.path.insert(0,str(V));import offline as old
j=old.j;sha=old.sha;digest=old.digest;Refusal=old.Refusal

def config():return j(D/'FINAL_RULE_TABLE.json')
def eval_node(n,ctx,cfg):
 if isinstance(n,bool):return n
 if 'op' not in n:return old.eval_node(n,ctx,cfg)
 op=n['op'];args=n['args']
 if op=='if':return eval_node(args[1] if eval_node(args[0],ctx,cfg) else args[2],ctx,cfg)
 a=[eval_node(x,ctx,cfg) for x in args]
 if op=='index':return a[0][a[1]]
 if op in ['and','or']:
  def fn(x,y):
   if type(x)is not bool or type(y)is not bool:raise Refusal('BOOLEAN_REQUIRED')
   return (x and y) if op=='and' else (x or y)
  z=a[0]
  for v in a[1:]:z=old.binary(fn,z,v)
  return z
 if op=='all':
  if not isinstance(a[0],list) or not a[0] or any(type(x)is not bool for x in a[0]):raise Refusal('BOOLEAN_SERIES_REQUIRED')
  return all(a[0])
 if op=='mean':return statistics.mean(a[0])
 if op=='first':return a[0][0]
 if op=='finite':return all(old.finite(x) for x in (a[0] if isinstance(a[0],list) else [a[0]]))
 if op=='abs':return [abs(v) for v in a[0]] if isinstance(a[0],list) else abs(a[0])
 if op in ['between','distance']:
  v,rg=a
  if len(rg)!=2 or rg[0]>rg[1]:raise Refusal('BAD_INTERVAL')
  f=(lambda x:rg[0]<=x<=rg[1]) if op=='between' else (lambda x:max(rg[0]-x,0,x-rg[1]))
  return [f(x) for x in v] if isinstance(v,list) else f(v)
 def div(x,y):
  if not old.finite(y) or y<=0:raise Refusal('NONPOSITIVE_DENOMINATOR')
  return x/y
 fs={'sub':lambda x,y:x-y,'mul':lambda x,y:x*y,'div':div,'ge':lambda x,y:x>=y,'gt':lambda x,y:x>y,'le':lambda x,y:x<=y,'lt':lambda x,y:x<y,'eq':lambda x,y:x==y}
 return old.binary(fs[op],*a)

def predicate(node,inputs):
 """Boolean definition checker for synthetic tests only; never called to label historical patients."""
 if isinstance(node,bool):return node
 if 'input'in node:
  value=inputs[node['input']]
  if type(value)is not bool:raise Refusal('PREDICATE_BOOLEAN_REQUIRED')
  return value
 if 'not'in node:return not predicate(node['not'],inputs)
 if 'and'in node:return all(predicate(x,inputs) for x in node['and'])
 raise Refusal('UNKNOWN_PREDICATE_NODE')

def verify_inputs():
 for p,h in j(D/'INPUT_SHA256.json').items():
  if sha(R/p)!=h:raise Refusal('PROTECTED_INPUT_HASH:'+p)

def validate(cfg):
 if len(cfg['rules'])!=14 or {r['rule_id'] for r in cfg['rules']}!={f'V2E-{i:02}' for i in range(1,15)}:raise Refusal('RULE_COVERAGE')
 def walk(x):
  if isinstance(x,bool):return
  if not isinstance(x,dict):raise Refusal('AST_LITERAL')
  if 'parameter'in x:
   if x['parameter'] not in cfg['parameter_registry']:raise Refusal('UNKNOWN_PARAMETER')
   if cfg['parameter_registry'][x['parameter']]['value'] is None:raise Refusal('UNDEFINED_PARAMETER')
  elif 'data'in x:
   if x['data'] not in cfg['metrics']:raise Refusal('UNKNOWN_METRIC')
  elif 'fact'in x:pass
  elif 'op'in x:
   for a in x['args']:walk(a)
  else:raise Refusal('INVALID_NODE')
 for r in cfg['rules']:
  for x in r['definitions'].values():walk(x)
  for x in r.get('oxygen_mode',{}).values():walk(x)
 return True

def checked_state(path):
 p=R/path;h=j(D/'INPUT_SHA256.json').get(path)
 if h is None or sha(p)!=h:raise Refusal('UNPINNED_OR_CHANGED_STATE:'+path)
 x=j(p)
 if not x['Version'].startswith('4.3.2'):raise Refusal('ENGINE_MISMATCH')
 return x,h

def add_fact(ctx,k,value,path,time):
 h=j(D/'INPUT_SHA256.json')[path]
 ctx['facts'][k]={'value':value,'source':path,'source_sha256':h,'observed_at_s':time,'available_at_s':time,'authorized':True}

def enrich(rec,cfg):
 ctx=rec['runtime_context'];rid=rec['rule_id'];audit={}
 if rid in ['V2E-07','V2E-08']:
  code='open_left' if rid=='V2E-07' else 'closed_left';path=str((C/'final_validation_v0.1/native'/code/'treatment/final_state.json').relative_to(R));s,h=checked_state(path)
  records=[x for x in j(V/'MECHANISM_SNAPSHOT_INDEX.json')['records'] if x['rule_id']==rid and x['branch']=='treatment'];t=records[0]['simulation_time_s']
  paths={x['CircuitPath']['Name']:x for x in s['CircuitManager']['FluidPath']}
  name='EnvironmentToLeftChestLeak' if rid=='V2E-07' else 'LeftNeedleToLeftPleural';p=paths[name]
  def resistance(k):
   x=p[k]['ScalarPressureTimePerVolume']
   if x['Unit']!='cmH2O s/L':raise Refusal('RESISTANCE_UNIT')
   return x['Value']
  current=resistance('Resistance');baseline=resistance('ResistanceBaseline')
  val=current==baseline if rid=='V2E-07' else current==old.value(cfg,'endpoint.needle_resistance') and current<baseline
  add_fact(ctx,'endpoint_chest_seal_proxy' if rid=='V2E-07' else 'endpoint_needle_patent_proxy',val,path,t)
  audit={'path':path,'sha256':h,'path_name':name,'current_resistance':current,'baseline_resistance':baseline,'unit':'cmH2O s/L','time_s':t,'claim':'endpoint circuit state proxy, NOT continuous sealing/clinical tension relief','next_state_not_substituted':True}
 if rid=='V2E-12':
  hpath='pulse/bin/states/StandardMale@0s.json';fpath=str((C/'final_lock_and_validation_v0.1/healthy_reference_run_v0.1/native/final_or_failed_state.json').relative_to(R));bpath=str((C/'final_validation_v0.1/native'/rec['case']/'treatment/accepted_state.json').relative_to(R))
  hs,hh=checked_state(hpath);fs,fh=checked_state(fpath);bs,bh=checked_state(bpath);tol=old.value(cfg,'reference.identity_relative_tolerance')
  # Match original demographics and model resting fluid identity, allowing only serialization roundoff.
  for s in [fs,bs]:
   for key in ['Age','Weight','Height','BodyFatFraction']:
    def same(a,b):
     if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
     if isinstance(a,(int,float)) and not isinstance(a,bool):return math.isclose(a,b,rel_tol=tol,abs_tol=0)
     return a==b
    if not same(hs['InitialPatient'][key],s['InitialPatient'][key]):raise Refusal('HEALTHY_PATIENT_MISMATCH')
   if not same(hs['Environment']['Common']['EnvironmentalConditions'],s['Environment']['Common']['EnvironmentalConditions']):
    # AirDensity is a derived system state, not an environmental input.
    a={k:v for k,v in hs['Environment']['Common']['EnvironmentalConditions'].items() if k!='AirDensity'};b={k:v for k,v in s['Environment']['Common']['EnvironmentalConditions'].items() if k!='AirDensity'}
    if not same(a,b):raise Refusal('HEALTHY_ENVIRONMENT_MISMATCH')
   if hs['InitialPatient'].get('Sex','Male')!=s['InitialPatient'].get('Sex','Male'):raise Refusal('HEALTHY_SEX_MISMATCH')
   if not math.isclose(hs['Tissue']['RestingFluidMass_kg'],s['Tissue']['RestingFluidMass_kg'],rel_tol=tol):raise Refusal('RESTING_FLUID_IDENTITY_MISMATCH')
  for s in [hs,fs]:
   if s.get('Conditions',{}).get('AnyCondition'):raise Refusal('HEALTHY_REFERENCE_HAS_CONDITION')
  def volume(s):
   x=s['Tissue']['Common']['TotalFluidVolume']['ScalarVolume']
   if x['Unit']!='mL':raise Refusal('HEALTHY_VOLUME_UNIT')
   return x['Value']
  lo=volume(hs);hi=volume(fs)
  if hi<lo:raise Refusal('REFERENCE_ENDPOINT_ORDER_CHANGED')
  # Reference clock separate from patient clock, using the already archived review envelope.
  env=j(V/'HEALTHY_REFERENCE_ENVELOPE.json')
  if ctx['use_mode']!='RETROSPECTIVE_RESEARCH' or datetime.datetime.fromisoformat(ctx['review_as_of_utc'])<datetime.datetime.fromisoformat(env['available_by_review_utc']):raise Refusal('REFERENCE_NOT_YET_AVAILABLE')
  add_fact(ctx,'matched_healthy_total_fluid_mL',lo,hpath,0)
  add_fact(ctx,'matched_healthy_total_fluid_upper_mL',hi,fpath,300)
  audit={'healthy_start_mL':lo,'healthy_end_mL':hi,'start_source':hpath,'end_source':fpath,'start_sha256':hh,'end_sha256':fh,'condition_state_sha256':bh,'resting_fluid_mass_kg':hs['Tissue']['RestingFluidMass_kg'],'identity_rounding_tolerance_ref':'reference.identity_relative_tolerance','coverage':'two sparse endpoints; NOT full healthy series','applicability':'PENDING','available_by_review_utc':env['available_by_review_utc']}
 rec['new_evidence']=audit
 return rec

def load_case(name,cfg=None):return enrich(old.load_case(name),cfg or config())

def evaluate_case(rec,cfg=None):
 cfg=cfg or config();ctx=rec['runtime_context'];rid=rec['rule_id'];r=next(x for x in cfg['rules'] if x['rule_id']==rid)
 # Reuse protected V2.2 checks and independent safety, not its grade construction or numeric goals.
 base=old.calculate(rec,'A',old.config())
 profile=copy.deepcopy(cfg['profile_safety'][rid+'/'+rec['case']]);scfg=copy.deepcopy(cfg)
 for key,target in profile['parameter_overrides'].items():scfg['parameter_registry'][key]=copy.deepcopy(cfg['parameter_registry'][target])
 base['safety']=old.safety(ctx,profile,scfg,rec['replay']['safety'])
 out={'rule_id':rid,'case':rec['case'],'version':cfg['version'],'config_sha256':digest(cfg),'parameter_sha256':digest(cfg['parameter_registry']),'safety':base['safety'],'source_sha256':base['evidence_quality']['source_sha256'],'execution':base['execution'],'evidence':rec.get('new_evidence',{}),'old_development_counterexample':rec['current_subconditions'],'subconditions':{},'formal_grade':None,'formal_scoring_enabled':False,'approval_status':'PENDING_OWNER_MEDICAL_APPROVAL','independent_validation':'PENDING','freeze_ready':False,'errors':[]}
 try:
  validate(cfg);old.validate_time(ctx,cfg)
  if rid=='V2E-08':old.reference_check(ctx,cfg)
  if base['evidence_quality']['errors']:
   if rid=='V2E-07' and base['candidate_grade']['status']!='NOT_EVALUABLE':out['supplementary_reference_errors']=base['evidence_quality']['errors']
   else:raise Refusal(';'.join(base['evidence_quality']['errors']))
  if not eval_node(r['definitions']['prerequisites'],ctx,cfg):raise Refusal('EXECUTION_PREREQUISITE')
  if not eval_node(r['definitions']['eligibility'],ctx,cfg):raise Refusal('MODE_OUTSIDE_DEFINED_SCOPE')
  # Explicit minimum and full evaluations both required; missing full cannot be turned into partial.
  for k in ['minimum','complete']:out['subconditions'][k]=eval_node(r['definitions'][k],ctx,cfg)
  if out['subconditions']['complete'] and not out['subconditions']['minimum']:raise Refusal('FULL_DOES_NOT_INCLUDE_MINIMUM')
  if rid=='V2E-09':out['oxygen_mode']='maintenance' if eval_node(r['oxygen_mode']['maintenance_eligible'],ctx,cfg) else 'improvement'
  if rid=='V2E-12':out['volume_deficit']={k:eval_node(v,ctx,cfg) for k,v in r['deficit_definitions'].items()}
  if out['safety']['required_missing']:raise Refusal('REQUIRED_SAFETY_DATA_MISSING:'+','.join(out['safety']['required_missing']))
  out['computation_state']='COMPUTABLE_SUBCONDITIONS_ONLY'
 except (Refusal,KeyError,TypeError,ValueError) as exc:out['errors'].append(str(exc));out['computation_state']='NOT_EVALUABLE'
 out['physiological_response']=base['physiological_response'].get('observed_changes',{})
 out['grade_applicability']={'E':'DEFINED','P':r['P_policy'],'I':'DEFINED'}
 return out

if __name__=='__main__':
 verify_inputs();cfg=config();names=[x['case'] for x in j(old.H/'COMPUTED_EVIDENCE.json')['cases']];results=[evaluate_case(load_case(n,cfg),cfg) for n in names]
 (D/'OFFLINE_RESULTS.json').write_text(json.dumps({'new_native_runs':0,'formal_labels':0,'cases':results},ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 print('completed',len(results),'offline archived views',[(x['case'],x['computation_state'],x['subconditions']) for x in results])
