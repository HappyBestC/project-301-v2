"""Offline evidence utilities. No simulator imports."""
import json,hashlib,sys,math,datetime
from numbers import Real,Integral
from pathlib import Path
D=Path(__file__).resolve().parent; C=D.parent; R=C.parents[1]; P=D; F=C/'final_rule_calibration_v1'
sys.path.insert(0,str(F));import calibrate as calc
Refusal=calc.Refusal
RULE_SHA='6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f'
def reject(x):raise Refusal(x)
def j(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def source(p):
 p=Path(p).resolve();return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def pinned(s):
 p=(R/s['path']).resolve()
 if not p.is_relative_to(R) or not p.is_file() or sha(p)!=s['sha256']:reject('SOURCE_SHA_MISMATCH:'+s['path'])
 return p
def load(s):return j(pinned(s))
def config():
 if sha(F/'FINAL_RULE_TABLE.json')!=RULE_SHA:reject('RULE_SNAPSHOT_CHANGED')
 return calc.config()
def finite(v):
 """Accept finite real scalars representable as JSON/Pulse doubles, never flags.
 NumPy real scalar types implement numbers.Real. Arrays, complex, strings,
 None, masked values and NumPy bool_ do not. Do not coerce those into data.
 """
 if isinstance(v,bool) or not isinstance(v,Real):return False
 try:return math.isfinite(float(v))
 except (ValueError,TypeError,OverflowError):return False

def numeric_or_none(v):
 """Normalize at the native boundary so NumPy float32/int64 are JSON-safe too."""
 if not finite(v):return None
 return int(v) if isinstance(v,Integral) else float(v)
CLOCK_TOL=config()['parameter_registry']['sampling.clock_tolerance_s']['value']
def close(a,b):return finite(a) and finite(b) and abs(a-b)<=CLOCK_TOL
def patient(s):
 p=load(s);p=p.get('InitialPatient',p.get('Patient',p));h=p['Height']['ScalarLength'];v=h['Value'];u=h['Unit']
 if u=='cm':v/=2.54
 elif u=='m':v*=100/2.54
 elif u!='in':reject('PATIENT_HEIGHT_UNIT')
 sex=p.get('Sex','Male')
 if sex not in ['Male','Female'] or not finite(v):reject('PATIENT_SEX_HEIGHT_INVALID')
 pbw=(45.5 if sex=='Female' else 50)+2.3*(v-60)
 if pbw<=0:reject('PATIENT_PBW_INVALID')
 return {'patient_id':p['Name'],'sex':sex,'height_in':v,'PBW_kg':pbw,'input_sha256':s['sha256'],'raw':p}
def environment(s):return {k:v for k,v in s['Environment']['Common']['EnvironmentalConditions'].items() if k!='AirDensity'}
def state_patient(s,ps):
 if not s.get('Version','').startswith('4.3.2'):reject('STATE_ENGINE_VERSION')
 a=s['InitialPatient'];b=ps['raw'];tol=config()['parameter_registry']['reference.identity_relative_tolerance']['value']
 def equal(a,b):
  if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
  if finite(a) and finite(b):return math.isclose(a,b,rel_tol=tol,abs_tol=0)
  return a==b
 if a.get('Name')!=ps['patient_id']:reject('STATE_PATIENT_NAME')
 if a.get('Sex','Male')!=ps['sex']:reject('STATE_PATIENT_SEX')
 # Weight is a model-adjusted state (shipped female 129.832lb vs requested130lb).
 # Its raw value is preserved, not used as an immutable patient-input discriminator.
 weight=a['Weight']['ScalarMass']
 if weight['Unit'] not in ['kg','lb'] or not finite(weight['Value']) or weight['Value']<=0:reject('STATE_WEIGHT_INVALID')
 for k in ['Age','Height','BodyFatFraction']:
  if not equal(a[k],b[k]):reject('STATE_PATIENT_IDENTITY:'+k)
 return True
def fact(value,s,t,available=None):return {'value':value,'source':s['path'],'source_sha256':s['sha256'],'observed_at_s':t,'available_at_s':t if available is None else available,'authorized':True}
def signed(decision,expected,trust,synthetic=False):
 """Trust roots are externally audited document hashes, never a user-supplied ACCEPT flag."""
 if trust.get('mode')=='SYNTHETIC_TEST_ONLY' and not synthetic:reject('SYNTHETIC_APPROVAL_FOR_REAL_DATA')
 if decision is None:reject('APPROVAL_PENDING')
 p=pinned(decision)
 if decision['sha256'] not in trust.get('trusted_decision_sha256',[]):reject('UNTRUSTED_APPROVAL')
 a=j(p)
 if a.get('decision')!='ACCEPT' or not a.get('signed_at') or not a.get('owner') or not a.get('domain_reviewer'):reject('APPROVAL_SIGNATURE_MISSING')
 if datetime.datetime.fromisoformat(a['signed_at']).utcoffset() is None:reject('APPROVAL_TIMEZONE_MISSING')
 for k,v in expected.items():
  if a.get(k)!=v:reject('APPROVAL_BINDING_MISMATCH:'+k)
 return a

def native_time(state):
 """ScalarTimeData proto3 omits Value at zero; this is not missing physiology."""
 x=state['SimulationTime']['ScalarTime']
 if x.get('Unit')!='s':reject('STATE_TIME_UNIT')
 value=x.get('Value',0)
 if not finite(value):reject('STATE_TIME_INVALID')
 return value
