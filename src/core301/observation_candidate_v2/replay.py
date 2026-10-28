"""Read-only frozen-evidence adapter, no engine creation and no efficacy scoring."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,math
from core301.paths import PROJECT_ROOT
from core301.contracts.observation import Measurement
from .catalog import INTERNAL
from .models import EvaluationObservationV2,EvaluationFrame,EventTransition,ActionReceipt,SourceSnapshot
from .projector import project,Access
MANIFEST=PROJECT_ROOT/'research_artifacts/v2_1_restricted_engineering_baseline_v1.0/PROJECT_FILES_SHA256.json'
MANIFEST_SHA='cc20589a11d92cf4ab69aec45f94b7009a648cae839117e92886afb8abdf908c'
@dataclass(frozen=True)
class ResearchAccess:
 patient_id:str
 branch_paths:frozenset[str]
 diagnostics:frozenset[str]
 events:bool=False
 actions:bool=False
 sources:bool=False
 def __post_init__(self):
  if type(self.branch_paths) is not frozenset or type(self.diagnostics) is not frozenset or not self.diagnostics<=set(INTERNAL):raise ValueError('Invalid research grant')
  if any(type(x) is not bool for x in (self.events,self.actions,self.sources)):raise ValueError('Boolean grants required')
class FrozenReader:
 def __init__(self):
  if hashlib.sha256(MANIFEST.read_bytes()).hexdigest()!=MANIFEST_SHA:raise ValueError('Baseline manifest changed')
  self.hashes=json.loads(MANIFEST.read_text());self.used={}
 def text(self,path):
  path=Path(path);path=path if path.is_absolute() else PROJECT_ROOT/path
  rel=str(path.relative_to(PROJECT_ROOT))
  if rel not in self.hashes or not path.is_file():raise ValueError('Untrusted/missing evidence')
  b=path.read_bytes()
  if rel not in self.hashes or hashlib.sha256(b).hexdigest()!=self.hashes[rel]:raise ValueError('Untrusted/changed evidence')
  self.used[rel]=self.hashes[rel];return b.decode()
 def json(self,path):return json.loads(self.text(path))
 def rows(self,path):return [json.loads(s) for s in self.text(path).splitlines()]
def load_branch(relative,grant,agent_access=None,reader=None):
 if not isinstance(grant,ResearchAccess) or relative not in grant.branch_paths:raise PermissionError('Research branch not granted')
 reader=reader or FrozenReader();d=PROJECT_ROOT/relative;n=d/'native' if (d/'native').is_dir() else d
 rows=reader.rows(n/'observations.jsonl');gaps=[];frames=[]
 previous=None;representative_line=None;duplicates=[]
 for line,row in enumerate(rows,1):
  if row['patient_id']!=grant.patient_id:raise ValueError('Patient mismatch')
  if previous is not None and row['time_s']==previous['time_s']:
   # Compare full raw records, including hidden fields, status and sample times.
   # Typed canonical JSON also distinguishes 1 from true (Python equality does not).
   if json.dumps(row,sort_keys=True,allow_nan=False)!=json.dumps(previous,sort_keys=True,allow_nan=False):raise ValueError('Conflicting same-time raw observation')
   duplicates.append({'line':line,'representative_line':representative_line,'simulation_time_s':row['time_s']})
   continue
  previous=row;representative_line=line
  ds={}
  for k in sorted(grant.diagnostics):
   value=row.get('diagnostics',{}).get(k)
   ds[k]=Measurement(value=value,status='available' if value is not None else 'unavailable',observed_at_s=row['time_s'] if k in row.get('diagnostics',{}) else None)
  frames.append(EvaluationFrame(patient=project(row,agent_access),diagnostics=ds))
 if duplicates:
  audit={'source_file':str((n/'observations.jsonl').relative_to(PROJECT_ROOT)),'patient_id':grant.patient_id,'branch':relative,'raw_records':len(rows),'merged_records':len(duplicates),'evaluation_frames':len(frames),'duplicates':duplicates}
  gaps.append('identical historical observation records merged: '+json.dumps(audit,sort_keys=True))
 missing={k for k in grant.diagnostics if any(f.diagnostics[k].value is None for f in frames)}
 gaps += ['diagnostic unavailable at some/all times: '+k for k in sorted(missing)]
 events=[]
 if grant.events:
  last={}
  # Preserve initial active duration, including events originating before the window.
  records=[{'time_s':rows[0]['time_s'],'events':rows[0]['events']}]+reader.rows(n/'native_events.jsonl')
  for r in records:
   now=r['events']
   for e in sorted(set(now)^set(last)):
    events.append(EventTransition(observed_at_s=r['time_s'],event=e,active=e in now,native_active_duration_s=now.get(e)))
   last=now
 actions=[]
 if grant.actions:
  for a in reader.json(n/'actions.json'):
   actions.append(ActionReceipt(observed_at_s=a['time_s'],phase=a['phase'],state=a['state']))
 sources=[]
 if grant.sources:
  for path in (n/'initial_state.json',n/'decision_state.json',d/'accepted_endpoint_state.json' if n!=d else n/'final_state.json'):
   if not path.exists():gaps.append('source snapshot missing: '+path.name);continue
   s=reader.json(path);names=[]
   for a in s.get('ActiveActions',{}).get('AnyAction',[]):
    for kind,v in a.get('PatientAction',{}).items():
     if kind in ('Hemorrhage','Hemothorax','TensionPneumothorax','RespiratoryFatigue','ImpairedAlveolarExchange'):
      names.append(':'.join([kind]+[str(v[k]) for k in ('Type','Side','Compartment') if k in v]))
   # Protobuf scalar zero omits Value, but the typed ScalarTime message must exist.
   scalar=s['SimulationTime']['ScalarTime']
   if scalar.get('Unit')!='s':raise ValueError('Unexpected native time unit')
   sources.append(SourceSnapshot(observed_at_s=scalar.get('Value',0.0),active_native_sources=names))
 return EvaluationObservationV2(patient_id=grant.patient_id,evidence_path=relative,frames=frames,events=events,actions=actions,source_snapshots=sources,gaps=gaps)
def match_pair(left,right,grant,reader=None):
 """Only compatibility of frozen comparisons; never labels a response effective."""
 if not isinstance(grant,ResearchAccess) or not {left,right}<=grant.branch_paths:raise PermissionError('Pair not granted')
 reader=reader or FrozenReader()
 def read(rel):
  d=PROJECT_ROOT/rel;n=d/'native' if (d/'native').is_dir() else d
  return reader.json(n/'configuration.json'),reader.rows(n/'observations.jsonl')
 a,x=read(left);b,y=read(right)
 # Two frozen descriptions of the same reviewed onset schedule; no generic field omission.
 aliases=[['StandardMale0','hemothorax60','open_pneumothorax540','decision660','end960'],['healthy0→60','hemothorax at60','advance540','open pneumothorax at540','decision660','endpoint960']]
 normalized=False
 if a!=b and a.get('profile_version')==b.get('profile_version')=='301.v2_1.thoracic.aligned_onsets.2' and a.get('initialization_order') in aliases and b.get('initialization_order') in aliases:
  a={**a,'initialization_order':aliases[0]};b={**b,'initialization_order':aliases[0]};normalized=True
 if a!=b:raise ValueError('Different fixed configurations')
 t=a['simulation_timeline']['decision_s']
 if any(r['patient_id']!=grant.patient_id for r in x+y):raise ValueError('Pair identity mismatch')
 rx=min(x,key=lambda r:abs(r['time_s']-t));ry=min(y,key=lambda r:abs(r['time_s']-t))
 if abs(rx['time_s']-t)>1e-7 or abs(ry['time_s']-t)>1e-7:raise ValueError('Missing aligned pretreatment sample')
 for group in ('values','diagnostics','events'):
  if rx[group].keys()!=ry[group].keys():raise ValueError('Pair missing fields')
  for k,v in rx[group].items():
   z=ry[group][k]
   if v is None or z is None:
    if v is not z:raise ValueError('Pair availability mismatch')
   elif type(v) not in (int,float) or type(z) not in (int,float) or not math.isfinite(v) or not math.isfinite(z) or abs(v-z)>1e-7:raise ValueError('Pretreatment mismatch')
 return {'left':left,'right':right,'configuration_matched':True,'pretreatment_matched':True,'precision':1e-7,'efficacy_evaluated':False,'reviewed_initialization_text_alias':normalized}
