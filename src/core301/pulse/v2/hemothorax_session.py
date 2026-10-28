"""Only native read paths and a strictly pretreatment-only state fork."""
import json,math,re
from pathlib import Path
from core301.pulse.session import PulseSession
from core301.pulse.v2.session import ResearchPulseSession, native_scalar
from core301.contracts.v2.hemothorax_observation import HemothoraxObservation
from core301.runtime.v2.errors import V2Error

DRAIN_REQUESTS=(
 ('residual_blood_volume_mL',{'Category':'Action','ActionName':'LeftHemothorax','PropertyName':'TotalBloodVolume','Unit':'mL'}),
 ('tube_flow_mL_min',{'Category':'Action','ActionName':'LeftTubeThoracostomy','PropertyName':'FlowRate','Unit':'mL/min'}),
 ('source_flow_mL_s',{'Category':'Action','ActionName':'LeftHemothorax','PropertyName':'FlowRate','Unit':'mL/s'}),
)

class _DrainNative(PulseSession):
    def _requests_json(self):
        p=json.loads(super()._requests_json());p['DataRequest'].extend(r for _,r in DRAIN_REQUESTS)
        return json.dumps(p)
    def _read(self):
        self._require_ready();v=self._engine.pull_data()
        if len(v)!=len(self.requested_fields)+len(DRAIN_REQUESTS)+1 or not math.isfinite(v[0]) or v[0]<0:
            raise V2Error('NATIVE_DATA_SHAPE','Invalid hemothorax native data')
        return v

class HemothoraxSession(ResearchPulseSession):
    def __init__(self,patient_id,requested_fields):
        super().__init__(patient_id,requested_fields)
        self._native=_DrainNative(patient_id,requested_fields=requested_fields)
        self._log_path=None
    def initialize(self,log_path,configuration=None):
        if configuration is not None:raise V2Error('UNVALIDATED_SCOPE','No hemothorax Condition initialization')
        self._log_path=Path(log_path)
        super().initialize(log_path)
        if self._native.get_timestep()!=.02:raise V2Error('UNVALIDATED_TIMESTEP','Only native .02s is audited')
    def diagnostics(self):
        v=self._native._read();offset=len(self._native.requested_fields)+1
        return {key:float(x) if math.isfinite(x) else None for (key,_),x in zip(DRAIN_REQUESTS,v[offset:])}
    def _restore_control(self,state):
        raise V2Error('UNSUPPORTED_RECOVERY','Use only the runtime-owned pretreatment fork')
    def _fork_pretreatment(self,state,log_path):
        if self._initialized:raise V2Error('ALREADY_INITIALIZED','Session cannot be replaced')
        data=json.loads(state)
        actions=data.get('ActiveActions',{}).get('AnyAction',[])
        patient=[x['PatientAction'] for x in actions if 'PatientAction' in x]
        if len(patient)!=1 or 'Hemothorax' not in patient[0]:
            raise V2Error('CONTROL_FORK_SCOPE','Exactly one active pretreatment source is required')
        h=patient[0]['Hemothorax']
        if h.get('Side')!='Left' or native_scalar(h,'Severity')!=.8 or native_scalar(h,'TotalBloodVolume') is None:
            raise V2Error('CONTROL_FORK_SCOPE','Wrong or inactive hemothorax source')
        # No native work before the exact treatment time and source checks pass.
        native_time=data.get('SimulationTime',{}).get('ScalarTime',{}).get('Value')
        if native_time is None or abs(native_time-660)>1e-6:
            raise V2Error('CONTROL_FORK_SCOPE','Only the 660s pretreatment state is supported')
        self._initialized=True;self._log_path=Path(log_path)
        self._native._create_engine(log_path)
        self._native.ready=bool(self._native._engine.serialize_from_string(state,self._native._requests_json(),self._native._format))
        if not self._native.ready:raise V2Error('INITIALIZATION_FAILED','Native fork failed')
        self._native._dt=self._native._engine.get_timestep('s')
        if self._native._dt!=.02:raise V2Error('UNVALIDATED_TIMESTEP','Unverified timestep')
    def drainage(self,epoch):
        now=self.get_simulation_time();s=self.execution_state();d=self.diagnostics()
        tubes=[x for x in s['actions'].get('TubeThoracostomy',[]) if x.get('Side')=='Left']
        sources=[x for x in s['actions'].get('Hemothorax',[]) if x.get('Side')=='Left']
        events=[]
        if self._log_path and self._log_path.exists():
            for line in self._log_path.read_text(errors='replace').splitlines():
                if 'Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.' in line:
                    m=re.search(r'\[([0-9.]+)\(s\)\]',line)
                    if m and float(m[1])<=now:events.append({'native_time_s':float(m[1]),'raw_log_line':line})
        def measurement(v):return {'value':v,'status':'available' if v is not None else 'unavailable','observed_at_s':now}
        v=d['residual_blood_volume_mL']
        return HemothoraxObservation(patient_id=self.patient_id,side='Left',simulation_time_s=now,session_epoch=epoch,
            residual_blood_volume_mL=measurement(v),source_flow_mL_s=measurement(d['source_flow_mL_s']),
            source_action_active=bool(sources),tube_action_active=bool(tubes),tube_flow_mL_min=d['tube_flow_mL_min'] if len(tubes)==1 else None,
            events=events,numeric_interpretation='unavailable' if v is None else 'negative_native_raw' if v<0 else 'native_raw')
