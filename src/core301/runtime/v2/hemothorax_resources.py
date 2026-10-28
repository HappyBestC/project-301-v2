"""Opt-in finite resources for engineering validation, not a production supply."""
from collections import Counter
from core301.runtime.v2.resources import ResearchResourceFixture, _Reservation
from .errors import V2Error

COSTS={
 'control_hemothorax_bleeding':({}, {'medic':1}, 'simulated_hemothorax_source_control'),
 'chest_tube':({'chest_tube_kit':1},{'medic':1},'research_chest_tube'),
}
class HemothoraxResources(ResearchResourceFixture):
    def snapshot(self,run_id,patient_id):
        with self._lock:
            result=super().snapshot(run_id,patient_id)
            reserved=sum((r.stock for r in self._reservations.values()),Counter())
            return result.model_copy(update={'chest_tube_kit':max(0,self.stock['chest_tube_kit']-reserved['chest_tube_kit'])})
    def reserve(self,plan_id,plan,run_id,patient_id):
        with self._lock:
            self._identity(run_id,patient_id)
            if plan_id in self._reservations:raise V2Error('RESOURCE_RESERVATION_DUPLICATE','Already reserved')
            demand=Counter();holds={}
            for a in plan.actions:
                if a.action_type not in COSTS or a.action_type not in self.capabilities:raise V2Error('CAPABILITY_UNAVAILABLE','Unverified action capability')
                stock,needed,permission=COSTS[a.action_type]
                if permission not in self.permissions:raise V2Error('PROCEDURE_NOT_AUTHORIZED','Missing explicit research permission')
                demand.update(stock)
                for k,v in needed.items():holds[k]=max(holds.get(k,0),v)
            reserved=sum((r.stock for r in self._reservations.values()),Counter());held=Counter()
            for r in self._reservations.values():held.update(r.holds)
            if any(self.stock[k]-reserved[k]<v for k,v in demand.items()) or any(self.holds.get(k,0)-held[k]<v for k,v in holds.items()):
                raise V2Error('RESOURCE_UNAVAILABLE','Whole-plan resources missing')
            self._reservations[plan_id]=_Reservation(demand,holds,{})
            return {'reserved_units':dict(demand),'held_units':holds,'production_inventory':False}
    def begin(self,plan_id,action_id,action_type):
        with self._lock:
            r=self._reservations[plan_id]
            if action_id in r.begun:raise V2Error('RESOURCE_REPLAY_BLOCKED','Already acquired')
            stock,_,permission=COSTS[action_type]
            if action_type not in self.capabilities or permission not in self.permissions:raise V2Error('RESOURCE_REVOKED','Research permission revoked')
            if any(self.stock[k]<v or r.stock[k]<v for k,v in stock.items()):raise V2Error('RESOURCE_UNAVAILABLE','Stock changed')
            for k,v in stock.items():self.stock[k]-=v;r.stock[k]-=v
            r.begun[action_id]={'allocated_units':dict(stock),'submission_status':'pending','delivery_status':'not_confirmed'}
            return r.begun[action_id].copy()

def validation_resources(run_id,patient_id):
    return HemothoraxResources(run_id,patient_id,stock={'chest_tube_kit':1},holds={'medic':1},capabilities=COSTS,
        permissions={'simulated_hemothorax_source_control','research_chest_tube'})
