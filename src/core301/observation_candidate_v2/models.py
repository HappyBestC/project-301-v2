from typing import Literal
from pydantic import Field, model_validator
from core301.contracts.base import Contract, PatientId, Time
from core301.contracts.observation import Measurement,Vitals,Circulation,Respiratory,Laboratory
from .catalog import INTERNAL
class LaboratoryV2(Laboratory):
 aorta_carboxyhemoglobin_concentration:Measurement|None=Field(default=None,exclude_if=lambda v:v is None)
 aorta_sodium_concentration:Measurement|None=Field(default=None,exclude_if=lambda v:v is None)
class PatientObservationV2(Contract):
 patient_id:PatientId
 simulation_time_s:Time
 vitals:Vitals
 circulation:Circulation|None=Field(default=None,exclude_if=lambda v:v is None)
 respiratory:Respiratory|None=Field(default=None,exclude_if=lambda v:v is None)
 laboratory:LaboratoryV2|None=Field(default=None,exclude_if=lambda v:v is None)
 @model_validator(mode='after')
 def validate_samples(self):
  for group in ('vitals','circulation','respiratory','laboratory'):
   obj=getattr(self,group)
   if obj is None:
    if group in self.model_fields_set:raise ValueError('Omit absent groups')
    continue
   for name in type(obj).model_fields:
    m=getattr(obj,name)
    if m is None:continue
    if m.observed_at_s is not None and m.observed_at_s>self.simulation_time_s:raise ValueError('Future measurement')
    if name in ('pulse_oximetry','inspired_oxygen_fraction') and m.value is not None and not 0<=m.value<=1:raise ValueError('Fraction outside [0,1]')
  return self
class EventTransition(Contract):
 observed_at_s:Time
 event:str
 active:bool
 native_active_duration_s:Time|None
 # These are read-after-step transition times, not rewritten text-log timestamps.
class ActionReceipt(Contract):
 observed_at_s:Time
 phase:str
 state:str
class SourceSnapshot(Contract):
 observed_at_s:Time
 active_native_sources:list[str]
 interpretation:Literal['PRESENCE_ONLY_NOT_CONTROL_SUCCESS']='PRESENCE_ONLY_NOT_CONTROL_SUCCESS'
class EvaluationFrame(Contract):
 patient:PatientObservationV2
 diagnostics:dict[str,Measurement]
 @model_validator(mode='after')
 def whitelist(self):
  if not set(self.diagnostics)<=set(INTERNAL):raise ValueError('Unknown internal metric')
  for m in self.diagnostics.values():
   if m.observed_at_s is not None and m.observed_at_s>self.patient.simulation_time_s:raise ValueError('Future diagnostic')
  return self
class EvaluationObservationV2(Contract):
 version:Literal['301.evaluation_observation.candidate.v2.1']='301.evaluation_observation.candidate.v2.1'
 patient_id:PatientId
 evidence_path:str
 frames:list[EvaluationFrame]
 events:list[EventTransition]
 actions:list[ActionReceipt]
 source_snapshots:list[SourceSnapshot]
 gaps:list[str]
 production_enabled:Literal[False]=False
 @model_validator(mode='after')
 def coherent(self):
  if not self.frames:raise ValueError('Empty history')
  ts=[f.patient.simulation_time_s for f in self.frames]
  if any(a>=b for a,b in zip(ts,ts[1:])):raise ValueError('Frame times must be strictly increasing')
  if any(f.patient.patient_id!=self.patient_id for f in self.frames):raise ValueError('Mixed patients')
  for records in (self.events,self.actions,self.source_snapshots):
   if any(a.observed_at_s>b.observed_at_s for a,b in zip(records,records[1:])):raise ValueError('Evidence times must be nondecreasing')
   if any(r.observed_at_s>ts[-1]+1e-7 for r in records):raise ValueError('Evidence beyond observation window')
  events={}
  for event in self.events:
   key=(event.observed_at_s,event.event)
   value=(event.active,event.native_active_duration_s)
   if key in events and events[key]!=value:raise ValueError('Conflicting same-time event')
   events[key]=value
  snapshots={}
  for snapshot in self.source_snapshots:
   key=snapshot.observed_at_s;value=frozenset(snapshot.active_native_sources)
   if key in snapshots and snapshots[key]!=value:raise ValueError('Conflicting same-time source snapshot')
   snapshots[key]=value
  # Receipts lack object/request identities. Preserve every receipt, but never
  # infer execution order or state transitions from list position at equal time.
  for a,b in zip(self.actions,self.actions[1:]):
   if a.observed_at_s==b.observed_at_s:
    gap=f'action order indeterminate at simulation_time_s={a.observed_at_s!r}: same-time receipts have no execution sequence'
    if gap not in self.gaps:self.gaps.append(gap)
  return self
