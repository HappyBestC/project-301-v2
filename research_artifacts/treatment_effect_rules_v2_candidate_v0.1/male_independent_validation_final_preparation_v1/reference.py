"""Patient-specific reference extraction and immutable attachment binding, no Pulse."""
import copy,statistics,sys
from common import *
sys.path.insert(0,str(C/'final_lock_and_validation_v0.1'));import healthy_analysis
EXTRACTION_VERSION='301.patient.reference.extractor.1'
STATES=['REFERENCE_NOT_AVAILABLE','REFERENCE_EXTRACTION_PENDING','REFERENCE_EXTRACTED','REFERENCE_TECHNICALLY_VALIDATED','REFERENCE_APPROVAL_PENDING','REFERENCE_APPROVED','REFERENCE_BOUND_AND_SEALED']
def algorithm_sha():return digest({'implementation':sha(Path(__file__)),'legacy_algorithm':sha(Path(healthy_analysis.__file__)),'identity_reader':sha(D/'common.py'),'rule_snapshot':RULE_SHA})
def fluid_volume(s):
 x=s['Tissue']['Common']['TotalFluidVolume']['ScalarVolume']
 if x['Unit']!='mL' or not finite(x['Value']) or x['Value']<=0:reject('FLUID_VOLUME_UNIT_OR_VALUE')
 return x['Value']
def extract(spec):
 # Inputs must be real archived source files or explicitly synthetic test artifacts.
 if spec['engine_version']!='4.3.2':reject('REFERENCE_ENGINE')
 if spec['data_kind'] not in ['HISTORICAL_REPLAY','SYNTHETIC_TEST_ONLY','AUTHORIZED_NATIVE']:reject('REFERENCE_DATA_KIND')
 if spec['data_kind']=='SYNTHETIC_TEST_ONLY' and spec['healthy_experiment_id']=='H00':reject('SYNTHETIC_CANNOT_BE_H00')
 if spec['rule_snapshot_sha256']!=RULE_SHA:reject('REFERENCE_RULE_VERSION')
 ps=patient(spec['patient_source']);s0=load(spec['initial_state']);s1=load(spec['final_state'])
 for st in [s0,s1]:
  state_patient(st,ps)
  if st.get('SYNTHETIC_TEST_ONLY') and spec['data_kind']!='SYNTHETIC_TEST_ONLY':reject('SYNTHETIC_STATE_FOR_REAL_REFERENCE')
  if st.get('Conditions',{}).get('AnyCondition') or st.get('ActiveActions',{}).get('AnyAction'):reject('HEALTHY_HAS_INJURY_OR_ACTION')
  if digest(environment(st))!=spec['environment_identity']:reject('REFERENCE_ENVIRONMENT')
  if not close(native_time(st),0 if st is s0 else 300):reject('HEALTHY_STATE_TIME')
  if st['SimulationTime']['ScalarTime']['Unit']!='s':reject('HEALTHY_TIME_UNIT')
 if not math.isclose(s0['Tissue']['RestingFluidMass_kg'],s1['Tissue']['RestingFluidMass_kg'],rel_tol=config()['parameter_registry']['reference.identity_relative_tolerance']['value']):reject('RESTING_FLUID_IDENTITY')
 rows=[json.loads(x) for x in pinned(spec['observations']).read_text().splitlines() if x.strip()]
 if not rows or not close(rows[0]['time_s'],180) or not close(rows[-1]['time_s'],300):reject('REFERENCE_RECORD_WINDOW')
 if spec['units']!={'pressure':'cmH2O','volume':'mL','fluid':'mL'}:reject('REFERENCE_UNITS')
 events=load(spec['events']);timing={'StartOfInhale','StartOfExhale','StartOfCardiacCycle'}
 if events.get('coverage_s')!=[0,300] or events.get('complete') is not True:reject('HEALTHY_EVENT_COVERAGE')
 previous=-math.inf
 for e in events['records']:
  if e['time_s']<=previous:reject('HEALTHY_EVENT_ORDER')
  previous=e['time_s']
  if not finite(e['time_s']) or not 0<=e['time_s']<=300+1e-6 or set(e['active_events'])-timing:reject('HEALTHY_PATHOLOGICAL_EVENT')
 if events.get('poll_count')!=15001 or events.get('dt_s')!=.02:reject('HEALTHY_EVENT_POLL_COVERAGE')
 idx=0;active=set()
 for row in rows:
  while idx<len(events['records']) and events['records'][idx]['time_s']<=row['time_s']+1e-6:
   active=set(events['records'][idx]['active_events']);idx+=1
  if active!=set(row['active_events']):reject('HEALTHY_PHASE_EVENT_INCONSISTENCY')
 plan=j(C/'final_lock_and_validation_v0.1/HEALTHY_COLLECTION_PLAN.json');result=healthy_analysis.analyze(rows,plan)
 if not result['candidate_stable']:reject('HEALTHY_CYCLES_UNSTABLE')
 lo=fluid_volume(s0);hi=fluid_volume(s1)
 if hi<lo:reject('FLUID_REFERENCE_ENDPOINT_ORDER_CHANGED')
 # Preserve continuous fluid drift when present, never substitute resting mass for volume.
 fs=load(spec['fluid_series'])
 if fs['unit']!='mL' or fs['field']!='Tissue.Common.TotalFluidVolume':reject('FLUID_SERIES_UNIT_OR_SOURCE')
 tt=[r['time_s'] for r in fs['rows']]
 if not tt or not close(tt[0],180) or not close(tt[-1],300) or any(not close(b-a,1) for a,b in zip(tt,tt[1:])):reject('HEALTHY_FLUID_GRID')
 vv=[r['value'] for r in fs['rows']]
 if not all(finite(v) and v>0 for v in vv) or not math.isclose(vv[-1],hi,rel_tol=1e-9):reject('HEALTHY_FLUID_VALUES')
 sources={k:spec[k] for k in ['patient_source','initial_state','final_state','observations','events','fluid_series']}
 if spec['data_kind']=='AUTHORIZED_NATIVE' or spec.get('supplemental_series'):
  if not spec.get('supplemental_series'):reject('HEALTHY_SUPPLEMENTAL_SOURCE_MISSING')
  extra=load(spec['supplemental_series']);erows=extra['rows']
  if len(erows)!=121 or any(not close(x['time_s'],180+i) for i,x in enumerate(erows)):reject('HEALTHY_SUPPLEMENTAL_GRID')
  for row in erows:
   for k,u in {'Na':'mEq/L','BV':'mL','ICF':'mL','ECF':'mL'}.items():
    v=row['measurements'].get(k,{})
    if v.get('unit')!=u or v.get('status')!='available' or not finite(v.get('value')) or v.get('sample_time_s')!=row['time_s']:reject('HEALTHY_SUPPLEMENTAL_DATA:'+k)
  sources['supplemental_series']=spec['supplemental_series']
 return {'reference_id':spec['healthy_experiment_id']+'.'+digest(sources)[:16],'patient_id':ps['patient_id'],'patient_input_sha256':ps['input_sha256'],'healthy_experiment_id':spec['healthy_experiment_id'],'engine_version':'4.3.2','environment_identity':spec['environment_identity'],'sampling_spec_sha256':digest(spec),'extraction_algorithm_sha256':algorithm_sha(),'extraction_version':EXTRACTION_VERSION,'source_data_sha256':sources,'rule_snapshot_sha256':RULE_SHA,'pressure_reference':{'unit':'cmH2O','kind':'ABSOLUTE_NOT_GAUGE','raw_range':[min(x['pressure_range'][0] for x in result['cycles']),max(x['pressure_range'][1] for x in result['cycles'])],'range':result['pressure_padded_candidate']},'volume_reference':{'unit':'mL','range':result['volume_padded_candidate']},'fluid_reference':{'unit':'mL','baseline_time_s':0,'upper_time_s':300,'baseline':lo,'upper':hi,'drift_mL':hi-lo,'continuous_record_s':[180,300],'continuous_range':[min(vv),max(vv)],'resting_fluid_mass_kg':s0['Tissue']['RestingFluidMass_kg'],'interpretation':'model healthy endpoints, not medical normal bounds; no mass-to-volume conversion'},'reference_time_window':[180,300],'reference_validation':result,'padding_applications':1,'approval_status':'PENDING','state':'REFERENCE_APPROVAL_PENDING','binding_sha256':None,'data_kind':spec['data_kind'],'extraction_spec':spec,'collected_at_utc':spec['collected_at_utc']}
def validate_attachment(ref,ps,env):
 for k in ['reference_id','healthy_experiment_id','source_data_sha256','sampling_spec_sha256','extraction_spec']:
  if not ref.get(k):reject('REFERENCE_SCHEMA:'+k)
 if ref['patient_id']!=ps['patient_id'] or ref['patient_input_sha256']!=ps['input_sha256']:reject('REFERENCE_PATIENT_MISMATCH')
 if ref['engine_version']!='4.3.2':reject('REFERENCE_ENGINE_MISMATCH')
 if ref['environment_identity']!=env:reject('REFERENCE_ENVIRONMENT_MISMATCH')
 if ref['rule_snapshot_sha256']!=RULE_SHA:reject('REFERENCE_RULE_MISMATCH')
 if ref['extraction_algorithm_sha256']!=algorithm_sha() or ref['extraction_version']!=EXTRACTION_VERSION:reject('REFERENCE_ALGORITHM_MISMATCH')
 if ref['reference_time_window']!=[180,300]:reject('REFERENCE_TIME_WINDOW')
 if ref['padding_applications']!=1:reject('REFERENCE_DOUBLE_PADDING')
 # Recompute from pinned sources, disallow hand-edited ranges, padding, identity or fluid anchors.
 actual=extract(ref['extraction_spec'])
 for k,v in actual.items():
  if k not in ['state','approval_status','binding_sha256'] and ref.get(k)!=v:reject('REFERENCE_RECOMPUTATION_MISMATCH:'+k)
 return True
def binding(ref_source,ps,env,policy_decision=None,reference_decision=None,trust=None,mode='AUTHORIZED_NATIVE'):
 ref=load(ref_source);validate_attachment(ref,ps,env);synthetic=mode=='SYNTHETIC_TEST_ONLY'
 if ref['data_kind']=='SYNTHETIC_TEST_ONLY' and not synthetic:reject('SYNTHETIC_REFERENCE_FOR_REAL_DATA')
 trust=trust or j(D/'TRUSTED_DECISIONS.json')
 policy=signed(policy_decision,{'scope':'PATIENT_REFERENCE_POLICY_A','rule_snapshot_sha256':RULE_SHA,'extraction_algorithm_sha256':algorithm_sha()},trust,synthetic)
 approval=signed(reference_decision,{'scope':'PATIENT_REFERENCE_APPLICABILITY','reference_sha256':ref_source['sha256'],'patient_input_sha256':ps['input_sha256']},trust,synthetic)
 if datetime.datetime.fromisoformat(policy['signed_at'])>datetime.datetime.fromisoformat(ref['collected_at_utc']):reject('POLICY_NOT_FIXED_BEFORE_COLLECTION')
 if datetime.datetime.fromisoformat(ref['collected_at_utc'])>datetime.datetime.fromisoformat(approval['signed_at']):reject('REFERENCE_APPROVED_BEFORE_COLLECTION')
 b={'rule_snapshot_sha256':RULE_SHA,'patient_id':ps['patient_id'],'patient_input_sha256':ps['input_sha256'],'healthy_reference_sha256':ref_source['sha256'],'extraction_version':EXTRACTION_VERSION,'extraction_algorithm_sha256':algorithm_sha(),'environment_identity':env,'policy_decision':policy_decision,'reference_decision':reference_decision,'state':'REFERENCE_BOUND_AND_SEALED','mode':mode,'reference_source':ref_source,'approved_at_utc':max(policy['signed_at'],approval['signed_at'],key=datetime.datetime.fromisoformat)}
 b['binding_sha256']=digest(b);return b

def validate_binding(b,trust=None):
 if b.get('binding_sha256')!=digest({k:v for k,v in b.items() if k!='binding_sha256'}):reject('BINDING_SHA_MISMATCH')
 ref=load(b['reference_source']);ps=patient(ref['extraction_spec']['patient_source'])
 rebuilt=binding(b['reference_source'],ps,b['environment_identity'],b['policy_decision'],b['reference_decision'],trust,b['mode'])
 if rebuilt!=b:reject('BINDING_RECOMPUTATION_MISMATCH')
 return True

def lifecycle(current,target,approved_binding=None,trust=None):
 if current not in STATES or target not in STATES or STATES.index(target)!=STATES.index(current)+1:reject('REFERENCE_LIFECYCLE_TRANSITION')
 if STATES.index(target)>=5:
  if not approved_binding:reject('REFERENCE_APPROVAL_PENDING')
  validate_binding(approved_binding,trust)
 return target

def seal_binding(path,b,trust=None):
 p=Path(path)
 if p.exists() and j(p)!=b:reject('SEALED_REFERENCE_REPLACEMENT')
 validate_binding(b,trust)
 if not p.exists():
  with p.open('x') as f:json.dump(b,f,indent=2)
