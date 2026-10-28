from dataclasses import dataclass
from core301.contracts.base import Time,PatientId
from core301.contracts.observation import Measurement
from pydantic import TypeAdapter
from .catalog import AGENT,BASIC,CONDITIONAL
from .models import PatientObservationV2
@dataclass(frozen=True)
class Access:
 """Trusted host grants, never inferred from known injury or action resources."""
 authorized:frozenset[str]=frozenset()
 relevant:frozenset[str]=frozenset()
 results_obtained:frozenset[str]=frozenset()
 disclose_unavailable:frozenset[str]=frozenset()
 def __post_init__(self):
  for v in (self.authorized,self.relevant,self.results_obtained,self.disclose_unavailable):
   if type(v) is not frozenset or not v<=CONDITIONAL:raise ValueError('Unknown/nonconditional grant')
def project(row,access=None):
 access=access or Access();time=TypeAdapter(Time).validate_python(row['time_s'],strict=True);pid=TypeAdapter(PatientId).validate_python(row['patient_id'],strict=True)
 result={'patient_id':pid,'simulation_time_s':time}
 visible=set(BASIC)|(access.authorized&access.relevant&(access.results_obtained|access.disclose_unavailable))
 for k in sorted(visible):
  spec=AGENT[k];group,key=k.split('.');raw=row.get(spec['raw_group'],{})
  sample_time=row.get('sample_times',{}).get(k,time)
  value=raw.get(spec['raw_key']);obtained=k in BASIC or k in access.results_obtained
  # Validate malformed provided numbers even when publication would be unavailable.
  if value is not None:Measurement(value=value,status='available',observed_at_s=sample_time)
  valid=obtained and value is not None
  if not valid and k not in BASIC and k not in access.disclose_unavailable:continue
  m=Measurement(value=value if valid else None,status='available' if valid else 'unavailable',observed_at_s=sample_time if spec['raw_key'] in raw else None)
  result.setdefault(group,{})[key]=m.model_dump()
 return PatientObservationV2.model_validate(result)
