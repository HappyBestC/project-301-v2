"""Offline expression interpreter; no native simulator, production evaluator or efficacy labels."""
import json,math,statistics,hashlib
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
class Refusal(ValueError):pass
def fail(code):raise Refusal(code)
def finite(x):return type(x) in (int,float) and math.isfinite(x)
def binary(fn,a,b):
 if isinstance(a,list) or isinstance(b,list):
  if isinstance(a,list) and isinstance(b,list):
   if len(a)!=len(b):fail('SERIES_LENGTH_MISMATCH')
   return [fn(x,y) for x,y in zip(a,b)]
  return [fn(x,b) for x in a] if isinstance(a,list) else [fn(a,y) for y in b]
 return fn(a,b)
def evaluate(node,ctx,rule,table):
 if not isinstance(node,dict):return node
 if 'parameter' in node:
  v=rule['parameters'].get(node['parameter'])
  if v is None:fail('THRESHOLD_UNDETERMINED:'+node['parameter'])
  return v
 if 'fact' in node:
  k=node['fact'];v=ctx.get('facts',{}).get(k)
  if not isinstance(v,dict) or 'value' not in v:fail('EVIDENCE_MISSING:'+k)
  if v.get('authorized') is not True:fail('UNAUTHORIZED_EVIDENCE:'+k)
  for t in ['observed_at_s','available_at_s']:
   if not finite(v.get(t)) or v[t]>ctx['query_time_s']:fail('FUTURE_OR_UNKNOWN_EVIDENCE:'+k)
  if not v.get('source') or not v.get('source_sha256'):fail('EVIDENCE_LINEAGE_MISSING:'+k)
  p=ROOT/v['source']
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=v['source_sha256']:fail('EVIDENCE_HASH_MISMATCH:'+k)
  return v['value']
 if 'data' in node:
  k=node['data'];w=node['window'];v=ctx.get(w,{}).get(k)
  if v is None:fail('DATA_MISSING:'+w+':'+k)
  if ctx.get('units',{}).get(k)!=table['metrics'][k]['unit']:fail('UNIT_MISMATCH:'+k)
  vals=v if isinstance(v,list) else [v]
  if not vals or not all(finite(x) for x in vals):fail('NONFINITE_OR_UNAVAILABLE:'+k)
  if w!='B' and len(vals)!=len(ctx['times'].get(w,[])):fail('SERIES_TIME_LENGTH_MISMATCH:'+w)
  return v
 name=node['op'];args=node['args']
 if name=='if':return evaluate(args[1] if evaluate(args[0],ctx,rule,table) else args[2],ctx,rule,table)
 a=[evaluate(x,ctx,rule,table) for x in args]
 if name in ['and','or']:
  if not all(type(x) is bool for x in a):fail('BOOLEAN_TYPE_REQUIRED')
  return all(a) if name=='and' else any(a)
 if name=='not':return not a[0]
 if name=='all':
  if not isinstance(a[0],list) or not a[0]:fail('EMPTY_ALL')
  return all(a[0])
 if name=='mean':
  if not isinstance(a[0],list) or not a[0]:fail('EMPTY_MEAN')
  return statistics.mean(a[0])
 if name=='first':return a[0][0]
 if name=='finite':return all(finite(x) for x in (a[0] if isinstance(a[0],list) else [a[0]]))
 if name=='abs':return [abs(x) for x in a[0]] if isinstance(a[0],list) else abs(a[0])
 if name in ['distance','between']:
  x,limits=a
  if len(limits)!=2 or not all(finite(y) for y in limits) or limits[0]>limits[1]:fail('INVALID_REFERENCE_INTERVAL')
  f=(lambda v:max(limits[0]-v,0,v-limits[1])) if name=='distance' else (lambda v:limits[0]<=v<=limits[1])
  return [f(v) for v in x] if isinstance(x,list) else f(x)
 def div(x,y):
  if not finite(y) or y<=0:fail('INVALID_DENOMINATOR_OR_MODE_UNDEFINED')
  return x/y
 ops={'sub':lambda x,y:x-y,'mul':lambda x,y:x*y,'div':div,'ge':lambda x,y:x>=y,'gt':lambda x,y:x>y,'le':lambda x,y:x<=y,'lt':lambda x,y:x<y,'eq':lambda x,y:x==y}
 if name not in ops:fail('UNKNOWN_OPERATOR:'+name)
 return binary(ops[name],*a)

def validate_context(ctx):
 for k in ['baseline_time_s','query_time_s','available_at_s']:
  if not finite(ctx.get(k)):fail('TIME_MISSING:'+k)
 if not ctx['baseline_time_s']<ctx['query_time_s']<=ctx['available_at_s']:fail('FUTURE_OR_INVALID_QUERY')
 for w,ts in ctx.get('times',{}).items():
  if not ts or not all(finite(x) for x in ts):fail('TIME_MISSING:'+w)
  if any(y<=x for x,y in zip(ts,ts[1:])):fail('DUPLICATE_OR_REVERSED_FRAME:'+w)
  if ts[-1]>ctx['query_time_s']:fail('FUTURE_FRAME:'+w)
  if ts[0]<=ctx['baseline_time_s']:fail('BASELINE_IN_POST_WINDOW:'+w)
  step=.02 if w=='H' else 1
  if w!='POST' and any(abs((y-x)-step)>1e-6 for x,y in zip(ts,ts[1:])):fail('GAP_OR_WRONG_GRID:'+w)
  if w=='POST' and any(y-x>1+1e-6 for x,y in zip(ts,ts[1:])):fail('POST_GAP')
  if w in ['W','H'] and (abs(ts[-1]-ctx['query_time_s'])>1e-6 or abs(ts[0]-(ctx['query_time_s']-60))>step+1e-6):fail('WRONG_WINDOW:'+w)
 if 'C' in ctx.get('times',{}) and ctx['times']['C']!=ctx['times'].get('W'):fail('CONTROL_WINDOW_MISMATCH')
 if 'W' not in ctx.get('times',{}):fail('WINDOW_MISSING')

def run(rule,ctx,table):
 out={'rule_id':rule['rule_id'],'subconditions':{},'reasons':[],'formal_label_generated':False,'safety':ctx.get('safety',{'state':'UNRESOLVED','reason':'POLICY_PENDING'}),'approval_status':rule['approval_status']}
 try:validate_context(ctx)
 except Refusal as e:out.update(status='NOT_EVALUABLE');out['reasons'].append(str(e));return out
 for key,node in rule['definitions'].items():
  try:out['subconditions'][key]=evaluate(node,ctx,rule,table)
  except (Refusal,KeyError,TypeError) as e:out['subconditions'][key]=None;out['reasons'].append(key+':'+str(e))
 s=out['subconditions']
 if out['reasons'] or s['prerequisites'] is not True:out['status']='NOT_EVALUABLE';out['reasons']+=['PREREQUISITE_NOT_MET'] if s['prerequisites'] is False else []
 elif not s['minimum']:out['status']='MINIMUM_NOT_MET'
 elif s['complete']:out['status']='COMPLETE_SUBCONDITIONS_MET'
 else:out['status']='MINIMUM_ONLY'
 out['mechanism_status']='UNKNOWN' if s['mechanism_minimum'] is None else 'TARGET_MET' if s['mechanism_minimum'] else 'TARGET_NOT_MET'
 out['formal_evaluation_blockers']=['OWNER_APPROVAL_PENDING','MEDICAL_SAFETY_PENDING','INDEPENDENT_VALIDATION_NOT_RUN','FORMAL_SCORING_DISABLED']
 return out

def resolve_safety(critical_events,required_missing,numeric_triggers,unmapped_events,policy_approved,critical_catalog):
 """Independent safety state; never an efficacy label."""
 if set(critical_events)&set(critical_catalog):return 'VETO'
 if required_missing or numeric_triggers or unmapped_events or not policy_approved:return 'UNRESOLVED'
 return 'NO_DEFINED_VETO_OBSERVED'
