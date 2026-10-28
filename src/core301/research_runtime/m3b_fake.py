"""Offline-only deterministic fault fixture; never physiological evidence."""
import copy
import json
from core301.pulse.observation_projector import Sample


class FakePulseWorker:
    native=False
    def __init__(self,run_id,patient_id,directory,fields,faults=None):
        self.run_id,self.patient_id=run_id,patient_id
        self.fields=fields;self.time=0.;self.ready=False;self.action_results=[]
        self.actions={};self.controlled=False;self.faults=faults or {};self.worker_pid=None
        self.execution_identity=None;self.closed=False
    def initialize(self,path,configuration=None):
        if self.faults.get('initialize'):raise RuntimeError('FAKE initialization failure')
        self.ready=True
    def get_simulation_time(self):return self.time
    def advance_time(self,seconds):
        if self.faults.get('advance_at') is not None and self.time+seconds>=self.faults['advance_at']:
            raise RuntimeError('FAKE advance/interruption')
        self.time+=seconds
        if self.faults.get('drift'):self.time+=.1
    def read_requested_data(self):return {k:Sample(1.,self.time) for k in self.fields}
    def diagnostics(self):return {'diagnostic.TotalHemorrhageRate':0. if self.controlled else 1.,'diagnostic.TotalHemorrhagedVolume':self.time,'diagnostic.BloodVolume':5000.}
    def active_events(self):return {}
    def execution_state(self):return {'actions':copy.deepcopy(self.actions),'airway_mode':'Free','intubation':'Off','diagnostics':self.diagnostics()}
    def serialize_state(self):return json.dumps({'FAKE':True,'patient_id':self.patient_id,'time_s':self.time,**self.execution_state()})
    def bind_execution(self,identity):
        if (identity['run_id'],identity['patient_id'])!=(self.run_id,self.patient_id):raise ValueError('Cross-patient execution binding')
        if self.execution_identity is not None and identity!=self.execution_identity:raise ValueError('Binding changed')
        self.execution_identity=dict(identity)
    def _submit(self,payload,phase):
        if phase=='treatment':
            if not self.execution_identity:raise ValueError('No execution binding')
            if self.faults.get('unknown'):raise RuntimeError('FAKE lost receipt; native outcome unknown')
            self.controlled=True;self.actions.pop('Hemorrhage',None)
        else:
            for name,body in payload['PatientAction'].items():self.actions[name]=[copy.deepcopy(body)]
        record={'phase':phase,'simulation_time_s':self.time,'accepted':True,'FAKE':True}
        self.action_results.append(record);return record
    def close(self):self.ready=False;self.closed=True
