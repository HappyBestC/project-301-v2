"""Manifest-driven readers and bridge to the unchanged final AST. Never emits grades."""
import copy,csv
from common import *
import reference

def read_rows(src,cfg):
 p=pinned(src)
 if src.get('format')=='csv':
  with p.open() as f:raw=list(csv.DictReader(f))
  rows=[]
  for line,row in enumerate(raw,2):
   t=float(row[src['time_column']]);ms={}
   for k,col in src['columns'].items():
    v=row[col['column']];ms[k]={'value':float(v) if v else None,'status':'available' if v else 'unavailable','unit':col['unit'],'sample_time_s':t}
   rows.append({'time_s':t,'available_at_s':t,'measurements':ms,'source_line':line})
 else:rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
 if not rows:reject('OBSERVATIONS_EMPTY')
 previous=None
 for row in rows:
  t=row['time_s']
  if not finite(t) or previous is not None and t<=previous:reject('DUPLICATE_OR_REVERSED_FRAME')
  previous=t
  if not finite(row.get('available_at_s')) or row['available_at_s']<t:reject('OBSERVATION_AVAILABILITY')
  for k,m in row['measurements'].items():
   if k not in cfg['metrics']:continue
   if m['unit']!=cfg['metrics'][k]['unit']:reject('UNIT_MISMATCH:'+k)
   if not finite(m.get('sample_time_s')) or m['sample_time_s']!=t:reject('STALE_OR_FUTURE_MEASUREMENT:'+k)
   if m.get('status') not in ['available','unavailable']:reject('MEASUREMENT_STATUS:'+k)
   if m.get('status')=='available' and not finite(m.get('value')):reject('NONFINITE:'+k)
 return rows

def event_history(src,baseline,end):
 ev=load(src)
 if ev.get('complete') is not True or len(ev.get('coverage_s',[]))!=2 or not close(ev['coverage_s'][0],baseline) or not close(ev['coverage_s'][1],end):reject('NATIVE_EVENT_HISTORY_MISSING')
 records=ev['records']
 if not records or not close(records[0]['time_s'],baseline):reject('INITIAL_ACTIVE_EVENTS_MISSING')
 prev=-math.inf
 for row in records:
  t=row['time_s']
  available=row.get('available_at_s',t)
  if not finite(t) or not finite(available) or available<t or t<prev or t>end or available>end:reject('EVENT_TIME_OR_FUTURE')
  if t==prev:reject('AMBIGUOUS_SAME_TIME_EVENT_SNAPSHOT')
  prev=t
  if not isinstance(row['active_events'],(dict,list)):reject('EVENTS_FORMAT')
 # Complete is a collector statement bound to SHA; actual polling contract separately preserved.
 return ev

def actions(src,expected,end):
 obj=load(src);receipts=obj['receipts']
 if len(receipts)!=len(expected):reject('ACTION_CHAIN_LENGTH')
 last_order=-1;last_time=-math.inf
 for actual,want in zip(receipts,expected):
  if actual.get('accepted') is not True:reject('ACTION_NOT_CONFIRMED')
  t=actual['simulation_time_s'];order=actual.get('order')
  available=actual.get('available_at_s')
  if not finite(t) or not finite(available) or available<t or t>end or available>end:reject('FUTURE_ACTION')
  if type(order)is not int or order<=last_order or t<last_time:reject('ACTION_ORDER_UNCONFIRMED')
  if not close(t,want['simulation_time_s']) or actual['payload']!=want['payload']:reject('ACTION_PAYLOAD_OR_TIME_MISMATCH')
  last_order=order;last_time=t
 return receipts

def matrix_experiment(name):return next(x for x in j(P/'EXPERIMENT_MATRIX.json')['experiments'] if x['experiment_id']==name)
def manifest_plan(man):
 cfg=config();rid=man['rule_id'];r=next(x for x in cfg['rules'] if x['rule_id']==rid);scope=r['fixed_scope']
 if man['rule_snapshot_sha256']!=RULE_SHA:reject('RULE_VERSION_MISMATCH')
 if man['data_kind'] not in ['AUTHORIZED_NATIVE','SYNTHETIC_TEST_ONLY']:reject('MANIFEST_DATA_KIND')
 if man['research_read_authorized'] is not True:reject('RESEARCH_ACCESS_DENIED')
 ep=matrix_experiment(man['experiment_id']);cp=matrix_experiment(man['control_experiment_id'])
 pair=next((x for x in j(P/'EXPERIMENT_MATRIX.json')['pairs'] if x['rule_id']==rid and x['treatment']==ep['experiment_id'] and x['control']==cp['experiment_id']),None)
 if not pair:reject('ILLEGAL_CONTROL_OR_ZERO_PAIR')
 for k,v in [('injury_type',scope['injury_type']),('profile',scope['profile']),('severity',ep['severity']),('injury_location',scope.get('location',{})),('action_time_s',ep['action_time']),('evaluation_end_s',ep['evaluation_window']['end_s'])]:
  if man.get(k)!=v:reject('MANIFEST_SCOPE_MISMATCH:'+k)
 if man['patient_source']['sha256']!=ep['patient_profile']['sha256']:reject('MANIFEST_PATIENT_INPUT')
 ps=patient(man['patient_source'])
 if ps['patient_id']!=man['patient_id']:reject('PATIENT_ID_MISMATCH')
 if man['engine_version']!='4.3.2':reject('MANIFEST_ENGINE_VERSION')
 if man['data_kind']=='SYNTHETIC_TEST_ONLY' and not man['dataset_id'].startswith('SYNTHETIC_TEST_ONLY'):reject('SYNTHETIC_DATASET_ID')
 return cfg,r,ep,cp,ps

def profile_key(rid,ep):
 suffix={4:'internal_zero',9:'hemothorax',10:'fatigue',11:'alveolar_'+str(ep['severity']),12:'dehydration_'+str(ep['severity'])}.get(int(rid[-2:]),rid)
 return rid+'/'+suffix

def normalized_conditions(value):
 # Only Pulse's exactly empty Dehydration base metadata is representation-only.
 value=copy.deepcopy(value)
 if isinstance(value,dict):
  for item in value.get('AnyCondition',[]):
   body=item.get('PatientCondition',{}).get('Dehydration',{})
   if body.get('PatientCondition')=={'Condition':{}}:body.pop('PatientCondition')
 return value

def branch(man,desc,ep,ps,cfg):
 if desc['experiment_id']!=ep['experiment_id'] or desc['patient_id']!=ps['patient_id'] or desc['data_kind']!=man['data_kind']:reject('BRANCH_IDENTITY_MISMATCH')
 if desc['patient_state_origin']!='FROM_PINNED_PATIENT_INPUT':reject('LEGACY_OR_SHIPPED_STATE_FOR_NEW_PATIENT')
 if desc['patient_input_sha256']!=ps['input_sha256'] or desc['engine_version']!='4.3.2':reject('BRANCH_PATIENT_OR_ENGINE')
 if desc['experiment_config_sha256']!=ep['input_sha256']:reject('BRANCH_INPUT_CONFIG_MISMATCH')
 initial=load(desc['initial_state']);pre=load(desc['pretreatment_state']);state_patient(initial,ps);state_patient(pre,ps)
 init=load(desc['initialization_receipt'])
 if init.get('accepted') is not True or init.get('patient_configuration_sha256')!=ep['initial_state']['patient_configuration_sha256'] or init.get('initial_state_sha256')!=desc['initial_state']['sha256'] or init.get('patient_input_sha256')!=ps['input_sha256']:reject('INITIALIZATION_PROVENANCE_MISMATCH')
 shipped={sha(p) for p in (R/'pulse/bin/states').glob('*@0s.json')}
 if desc['initial_state']['sha256'] in shipped:reject('SHIPPED_STATE_NOT_NEW_INITIALIZATION')
 if ep['group']=='dehydration' and normalized_conditions(initial.get('Conditions'))!=normalized_conditions(ep['patient_configuration'].get('Conditions')):reject('INITIAL_CONDITION_MISMATCH')
 if ep['group'] in ['external','internal']:
  sources=[x['PatientAction']['Hemorrhage'] for x in pre.get('ActiveActions',{}).get('AnyAction',[]) if 'Hemorrhage' in x.get('PatientAction',{})]
  expected=ep['injury']['PatientAction']['Hemorrhage']
  if len(sources)!=1 or sources[0].get('Compartment')!=expected['Compartment'] or sources[0].get('Severity')!=expected['Severity']:reject('PRETREATMENT_SOURCE_IDENTITY_MISMATCH')
 if not close(pre['SimulationTime']['ScalarTime']['Value'],man['action_time_s']):reject('PRETREATMENT_TIME')
 if desc['injury_evidence']['configuration']!=ep['injury'] or desc['injury_evidence']['conditions']!=ep['patient_configuration'].get('Conditions'):reject('INJURY_OR_CONDITION_MISMATCH')
 injury=load(desc['injury_evidence']['source'])
 if ep['injury']:
  actions(desc['injury_evidence']['source'],[{'payload':ep['injury'],'simulation_time_s':ep['injury_time_s']}],man['action_time_s'])
 else:
  if injury.get('Conditions')!=ep['patient_configuration'].get('Conditions'):reject('CONDITION_STATE_MISMATCH')
 rows=read_rows(desc['observations'],cfg);b=man['action_time_s'];q=man['evaluation_end_s']
 if not close(rows[0]['time_s'],b) or not close(rows[-1]['time_s'],q):reject('BASELINE_OR_END_MISSING')
 actual_end=rows[-1]['time_s']
 if any(x['available_at_s']>actual_end for x in rows):reject('FUTURE_OBSERVATION')
 if any(not close(y['time_s']-x['time_s'],1) for x,y in zip(rows,rows[1:])):reject('PUBLIC_SAMPLING_GAP')
 rec=actions(desc['actions'],ep['treatment'],actual_end);ev=event_history(desc['events'],rows[0]['time_s'],actual_end)
 return {'rows':rows,'actions':rec,'events':ev,'state':pre,'environment':digest(environment(initial))}

def event_window_fact(events,src,start,query):
 """Derived fact binds the last actual snapshot, never a planned endpoint."""
 records=events['records']
 if not records or records[-1]['time_s']!=query:reject('EVENT_ENDPOINT_NOT_OBSERVED')
 active=set();hit=False
 for row in records:
  t=row['time_s'];available=row.get('available_at_s',t)
  if not finite(t) or not finite(available) or available<t or t>query or available>query:reject('EVENT_TIME_OR_FUTURE')
  if t<=start:active=set(row['active_events'])
  if t>=start and set(row['active_events'])&{'Hypoxia','BrainOxygenDeficit','CriticalBrainOxygenDeficit'}:hit=True
 hit=hit or bool(active&{'Hypoxia','BrainOxygenDeficit','CriticalBrainOxygenDeficit'})
 return fact(not hit,src,records[-1]['time_s'],max(x.get('available_at_s',x['time_s']) for x in records))


def assemble(man,trust=None,evidence_contract=None):
 cfg,r,ep,cp,ps=manifest_plan(man)
 execution_source=None
 if evidence_contract is not None:execution_source=evidence_contract.execution(man,ep,cp)
 elif man['data_kind']=='AUTHORIZED_NATIVE':reject('TRACEABLE_EXECUTION_CONTEXT_REQUIRED')
 rid=man['rule_id'];b=man['action_time_s'];q=man['evaluation_end_s']
 t=branch(man,man['treatment'],ep,ps,cfg);c=branch(man,man['control'],cp,ps,cfg)
 for k in ['initial_state','pretreatment_state']:
  if man['treatment'][k]['sha256']!=man['control'][k]['sha256']:reject('CONTROL_INITIAL_STATE_MISMATCH')
 if t['environment']!=c['environment']:reject('CONTROL_ENVIRONMENT_MISMATCH')
 def values(row):return {k:(v['value'] if v.get('status')=='available' else None) for k,v in row['measurements'].items() if k in cfg['metrics']}
 if [x['time_s'] for x in t['rows']]!=[x['time_s'] for x in c['rows']]:reject('CONTROL_TIME_GRID_MISMATCH')
 if values(t['rows'][0])!=values(c['rows'][0]):reject('CONTROL_BASELINE_VALUES_MISMATCH')
 tail=cfg['parameter_registry']['window.tail_s']['value'];w=[x for x in t['rows'] if x['time_s']>=q-tail-1e-6];cc=[x for x in c['rows'] if x['time_s']>=q-tail-1e-6];post=t['rows'][1:]
 ctx={'rule_id':rid,'case_id':man['experiment_id'],'baseline_time_s':t['rows'][0]['time_s'],'query_time_s':t['rows'][-1]['time_s'],'available_at_s':t['rows'][-1]['available_at_s'],'units':{k:v['unit'] for k,v in cfg['metrics'].items()},'B':values(t['rows'][0]),'times':{},'facts':{},'pairing':{'verified':True,'shared_baseline':True,'rule_id':rid,'case_id':man['experiment_id']}}
 for name,rows in [('W',w),('C',cc),('POST',post)]:
  ctx['times'][name]=[x['time_s'] for x in rows];ctx[name]={k:[values(x).get(k) for x in rows] for k in cfg['metrics'] if k!='elapsed_s'}
 ctx['POST']['elapsed_s']=[x-ctx['baseline_time_s'] for x in ctx['times']['POST']]
 query=ctx['query_time_s']
 if rid in ['V2E-07','V2E-08']:
  circuit_rows=[json.loads(line) for line in pinned(man['treatment']['circuit_observations']).read_text().splitlines() if line.strip()]
  if not circuit_rows or not close(circuit_rows[0]['time_s'],b) or not close(circuit_rows[-1]['time_s'],q):reject('CIRCUIT_WINDOW_INCOMPLETE')
  if any(not close(y['time_s']-x['time_s'],.02) for x,y in zip(circuit_rows,circuit_rows[1:])):reject('CIRCUIT_GRID')
  if any(not finite(x.get('available_at_s')) or x['available_at_s']<x['time_s'] or x['available_at_s']>query or x['time_s']>query or x.get('missing_paths') for x in circuit_rows):reject('CIRCUIT_FUTURE_OR_PATH_MISSING')
  rr=read_rows(man['treatment']['pleural_observations'],cfg)
  if any(x['available_at_s']>query or x['time_s']>query for x in rr):reject('FUTURE_PLEURAL_FRAME')
  rr=[x for x in rr if x['time_s']>=q-tail-1e-6];ctx['times']['H']=[x['time_s'] for x in rr];ctx['H']={k:[values(x).get(k) for x in rr] for k in ['pressure','volume']}
 src=man['treatment']['actions'];fs=ctx['facts']
 action_time=max((x['simulation_time_s'] for x in t['actions']),default=t['rows'][0]['time_s'])
 action_available=max((x['available_at_s'] for x in t['actions']),default=t['rows'][0]['available_at_s'])
 for k in ['scope_valid','execution_valid','authorization_valid','single_source_identity_valid','side_valid','matched_zero_valid','support_exclusivity_valid']:
  fs[k]=fact(True,src,action_time,action_available)
 if execution_source is not None:fs['authorization_valid']=fact(True,execution_source,ctx['query_time_s'])
 if rid in ['V2E-02','V2E-03','V2E-05','V2E-06']:
  # Execution context does not assert physiological restoration or invent intermediate B.
  if not t['actions'] or t['actions'][0]['payload']!=c['actions'][0]['payload']:reject('SOURCE_CONTROL_CONTEXT_MISMATCH')
  fs['source_controlled_context_valid']=fact(True,src,action_time,action_available)
 if rid=='V2E-10':fs['patient_PBW_kg']=fact(ps['PBW_kg'],man['patient_source'],b)
 final=load(man['treatment']['final_state']);state_patient(final,ps)
 final_time=final['SimulationTime']['ScalarTime']['Value']
 if not close(final_time,q) or final_time>query:reject('FINAL_STATE_TIME')
 if rid in ['V2E-07','V2E-08']:
  name='EnvironmentToLeftChestLeak' if rid=='V2E-07' else 'LeftNeedleToLeftPleural'
  path=next(x for x in final['CircuitManager']['FluidPath'] if x['CircuitPath']['Name']==name)
  if circuit_rows[-1]['paths'][name]!=path:reject('CIRCUIT_ENDPOINT_STATE_MISMATCH')
  def res(k):
   x=path[k]['ScalarPressureTimePerVolume']
   if x['Unit']!='cmH2O s/L' or not finite(x.get('Value')):reject('RESISTANCE_UNIT_OR_MISSING')
   return x['Value']
  v=res('Resistance')==res('ResistanceBaseline') if rid=='V2E-07' else res('Resistance')==cfg['parameter_registry']['endpoint.needle_resistance']['value'] and res('Resistance')<res('ResistanceBaseline')
  fs['endpoint_chest_seal_proxy' if rid=='V2E-07' else 'endpoint_needle_patent_proxy']=fact(v,man['treatment']['final_state'],final_time)
 if rid in ['V2E-10','V2E-11']:
  aa=final['ActiveActions']['AnyAction'];needle='MechanicalVentilator' if rid=='V2E-10' else 'SupplementalOxygen'
  confirmed=any(needle in json.dumps(x) for x in aa)
  fs['ventilation_support_confirmed' if rid=='V2E-10' else 'oxygen_support_confirmed']=fact(confirmed,man['treatment']['final_state'],final['SimulationTime']['ScalarTime']['Value'])
 if rid=='V2E-09':
  ev=load(man['treatment']['E1_evidence'])
  if not finite(ev['available_at_s']) or not finite(ev['observed_at_s']) or ev['available_at_s']<ev['observed_at_s'] or ev['available_at_s']>query or ev['observed_at_s']>query:reject('FUTURE_E1_EVIDENCE')
  raw=load(ev['samples_source'])
  sys.path.insert(0,str(R/'src'))
  from core301.pulse.v2.hemothorax_endpoint_review import review_endpoints
  if any(x['patient_id']!=ps['patient_id'] for x in raw):reject('E1_PATIENT_MISMATCH')
  if any(not finite(x.get('simulation_time_s')) or x['simulation_time_s']>query for x in raw):reject('FUTURE_E1_SAMPLE')
  result=review_endpoints(raw,configuration=ev['configuration'],safety_events=[],physiology_complete=True)
  fs['E1_complete']=fact(result['local_control_supported'],man['treatment']['E1_evidence'],ev['observed_at_s'],ev['available_at_s'])
  auto=any('Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.' in x['raw_log_line'] for row in raw for x in row['events'])
  fs['native_auto_stop_confirmed']=fact(auto,man['treatment']['E1_evidence'],ev['observed_at_s'],ev['available_at_s'])
 if rid=='V2E-14':
  fs['target_events_inactive_W']=event_window_fact(t['events'],man['treatment']['events'],w[0]['time_s'],query)
 reference_binding=None
 if (evidence_contract.requires_reference(rid) if evidence_contract is not None else rid in ['V2E-07','V2E-08','V2E-12']):
  if not man.get('healthy_reference'):reject('REFERENCE_NOT_AVAILABLE')
  # Match healthy environment, not hazardous gas environment; these three profiles keep environment unchanged.
  reference_binding=evidence_contract.reference(man,ps,t['environment']) if evidence_contract is not None else reference.binding(man['healthy_reference'],ps,t['environment'],man.get('reference_policy_approval'),man.get('reference_approval'),trust,man['data_kind'])
  ref=load(man['healthy_reference'])
  if evidence_contract is None and datetime.datetime.fromisoformat(reference_binding['approved_at_utc'])>=datetime.datetime.fromisoformat(man['response_started_at_utc']):reject('REFERENCE_NOT_BOUND_BEFORE_RESPONSE')
  if rid=='V2E-12':
   if not math.isclose(t['state']['Tissue']['RestingFluidMass_kg'],ref['fluid_reference']['resting_fluid_mass_kg'],rel_tol=cfg['parameter_registry']['reference.identity_relative_tolerance']['value']):reject('RESTING_FLUID_IDENTITY_MISMATCH')
   # Separate reference clock: pre-approved offline attachment available before any response.
   fs['matched_healthy_total_fluid_mL']=fact(ref['fluid_reference']['baseline'],man['healthy_reference'],b)
   fs['matched_healthy_total_fluid_upper_mL']=fact(ref['fluid_reference']['upper'],man['healthy_reference'],b)
  else:
   cfg=copy.deepcopy(cfg)
   for key,field in [('reference.pressure_final_range','pressure_reference'),('reference.volume_final_range','volume_reference')]:cfg['parameter_registry'][key]['value']=ref[field]['range']
 calc.old.validate_time(ctx,cfg)
 return ctx,cfg,profile_key(rid,ep),t['events'],reference_binding,ps

def compute(ctx,cfg,key,events):
 """Only the existing AST evaluates goals. No new efficacy formula or grade logic."""
 rid=ctx['rule_id'];rule=next(x for x in cfg['rules'] if x['rule_id']==rid);scfg=copy.deepcopy(cfg);profile=cfg['profile_safety'][key]
 for k,target in profile['parameter_overrides'].items():scfg['parameter_registry'][k]=copy.deepcopy(cfg['parameter_registry'][target])
 names=set()
 for row in events.get('records',[]):names.update(row['active_events'])
 safety=calc.old.safety(ctx,profile,scfg,{'native_events_retained':events,'confirmed_critical_events':sorted(names&set(profile['critical_events']))})
 out={'rule_id':rid,'formal_grade':None,'formal_scoring_enabled':False,'freeze_ready':False,'approval_status':'PENDING','safety':safety,'subconditions':{},'errors':[],'rule_snapshot_sha256':RULE_SHA,'base_parameter_sha256':digest(config()['parameter_registry']),'effective_context_parameter_sha256':digest(cfg['parameter_registry'])}
 try:
  calc.validate(cfg);calc.old.validate_time(ctx,cfg)
  for k in ['prerequisites','eligibility']:
   if calc.eval_node(rule['definitions'][k],ctx,cfg) is not True:reject(k.upper()+'_NOT_MET')
  out['subconditions']={k:calc.eval_node(rule['definitions'][k],ctx,cfg) for k in ['minimum','complete']}
  if out['subconditions']['complete'] and not out['subconditions']['minimum']:reject('FULL_DOES_NOT_INCLUDE_MINIMUM')
  if safety['required_missing']:reject('REQUIRED_SAFETY_DATA_MISSING:'+','.join(safety['required_missing']))
  out['computation_state']='COMPUTABLE_SUBCONDITIONS_ONLY'
 except (Refusal,KeyError,ValueError,TypeError) as e:out['computation_state']='NOT_EVALUABLE';out['errors'].append(str(e))
 return out

def evaluate(man,trust=None,evidence_contract=None):
 out={'rule_id':man.get('rule_id'),'formal_grade':None,'formal_scoring_enabled':False,'computation_state':'NOT_EVALUABLE','subconditions':{},'errors':[],'safety':{'state':'UNRESOLVED','native_events':[]}}
 # Retain confirmed events even if other evidence is absent or refused.
 try:
  ev=load(man['treatment']['events']);out['safety']['native_events']=ev
  names=set(n for e in ev.get('records',[]) for n in e.get('active_events',[]));critical=set(next(iter(config()['profile_safety'].values()))['critical_events'])&names
  if critical:out['safety'].update(state='VETO',confirmed_critical_events=sorted(critical))
 except (Refusal,KeyError,ValueError,TypeError) as e:out['errors'].append('NATIVE_EVENTS:'+str(e))
 try:
  ctx,cfg,key,ev,binding,ps=assemble(man,trust,evidence_contract);result=compute(ctx,cfg,key,ev);result.update(reference_binding=binding,patient={k:v for k,v in ps.items() if k!='raw'},data_kind=man['data_kind'],manifest_sha256=digest(man));return result
 except (Refusal,KeyError,ValueError,TypeError,StopIteration,OSError) as e:out['errors'].append(str(e));return out

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('manifest');args=a.parse_args();print(json.dumps(evaluate(j(args.manifest)),indent=2,ensure_ascii=False))

