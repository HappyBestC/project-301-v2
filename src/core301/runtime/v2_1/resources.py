"""One trusted host grant and one whole-sequence reservation per patient case."""
from collections import Counter
from core301.runtime.v2.resources import COSTS as BASE
from core301.runtime.v2.hemothorax_resources import COSTS as HEMO
from core301.runtime.v2.errors import V2Error
from .contracts import HostResources
COSTS={**BASE,**HEMO,'remove_from_exposure':({}, {'evacuation_team':1},'research_environment_removal')}
class Resources:
 def __init__(self,grant,run_id,patient_id):
  self.grant=HostResources.model_validate(grant).model_copy(deep=True) if grant is not None else None
  if self.grant and (self.grant.run_id,self.grant.patient_id)!=(run_id,patient_id):raise V2Error('RESOURCE_IDENTITY_MISMATCH','Wrong host grant')
  if self.grant and any(type(v) is not int or v<0 for v in [*self.grant.stock.values(),*self.grant.holds.values()]):raise V2Error('INVALID_RESOURCE','Nonnegative integer resources required')
  self.record=None
 def reserve(self,kinds):
  if self.record is not None:raise V2Error('RESOURCE_BUSY','One allocation per episode')
  g=self.grant
  if g is None:raise V2Error('RESOURCE_UNAVAILABLE','No implicit supplies')
  demand=Counter();holds={}
  for k in kinds:
   if k not in COSTS or k not in g.capabilities:raise V2Error('CAPABILITY_UNAVAILABLE',k)
   st,hd,permission=COSTS[k]
   if permission and permission not in g.permissions:raise V2Error('PROCEDURE_NOT_AUTHORIZED',k)
   if k=='remove_from_exposure' and not (g.protected_route_available and g.receiving_environment_verified):raise V2Error('RESOURCE_UNAVAILABLE','Route and receiving environment required')
   demand.update(st)
   for name,n in hd.items():holds[name]=max(holds.get(name,0),n)
  if any(g.stock.get(k,0)<n for k,n in demand.items()) or any(g.holds.get(k,0)<n for k,n in holds.items()):raise V2Error('RESOURCE_UNAVAILABLE','Insufficient stock/equipment/team')
  self.record={'reserved':dict(demand),'held':holds,'allocated':[],'production_inventory':False}
  return self.record
 def begin(self,kind):
  st,_,permission=COSTS[kind];g=self.grant
  if kind not in g.capabilities or permission and permission not in g.permissions:raise V2Error('RESOURCE_REVOKED',kind)
  if any(g.stock.get(k,0)<v for k,v in st.items()):raise V2Error('RESOURCE_UNAVAILABLE','Inventory changed')
  for k,v in st.items():g.stock[k]-=v
  item={'kind':kind,'units':st.copy(),'delivery':'UNKNOWN'};self.record['allocated'].append(item);return item
 def close(self):
  self.closed=True  # Closure audit must not mutate an already returned request receipt.

def study_resources(run_id,patient_id):
 return HostResources(run_id=run_id,patient_id=patient_id,stock={'saline_500ml_bag':1,'blood_500ml_bag':1,'airway_kit':1,'occlusive_dressing_kit':1,'needle_kit':1,'chest_tube_kit':1},holds={'medic':1,'ventilator':1,'nasal_cannula':1,'oxygen_425l_source':1,'evacuation_team':1},capabilities=frozenset(COSTS),permissions=frozenset(p for _,_,p in COSTS.values() if p),protected_route_available=True,receiving_environment_verified=True)
