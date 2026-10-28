"""Native CO/ambient oxygen read paths and fixed environmental action adapter."""
import json,math
from types import MappingProxyType
from core301.pulse.session import PulseSession
from core301.pulse.v2.session import ResearchPulseSession, native_scalar
from core301.pulse.injury_adapter import scalar
from core301.runtime.v2.errors import V2Error
from core301.contracts.v2.exposure_validation import ExposureObservation

PROFILE='301.v2.environment.validation.1'
# (CO fraction, O2 fraction, healthy seconds, exposure seconds, response seconds)
PROFILES=MappingProxyType({'carbon_monoxide_exposure':(.005,.21,60,900,900),
                          'environmental_hypoxia':(0,.12,60,300,300)})
EXPOSURE_REQUESTS=(
 ('aorta_co_saturation',{'Category':'LiquidCompartment','CompartmentName':'Aorta','SubstanceName':'CarbonMonoxide','PropertyName':'Saturation'}),
 ('aorta_cohb_g_dL',{'Category':'LiquidCompartment','CompartmentName':'Aorta','SubstanceName':'Carboxyhemoglobin','PropertyName':'Concentration','Unit':'g/dL'}),
 ('oxygen_saturation',{'Category':'Physiology','PropertyName':'OxygenSaturation'}),
 ('aorta_sodium_mEq_L',{'Category':'LiquidCompartment','CompartmentName':'Aorta','SubstanceName':'Sodium','PropertyName':'Molarity','Unit':'mEq/L'}),
 ('ambient_co_fraction',{'Category':'GasCompartment','CompartmentName':'Ambient','SubstanceName':'CarbonMonoxide','PropertyName':'VolumeFraction'}),
 ('ambient_oxygen_fraction',{'Category':'GasCompartment','CompartmentName':'Ambient','SubstanceName':'Oxygen','PropertyName':'VolumeFraction'}),
)

def environment_action(co,oxygen):
    return {'EnvironmentAction':{'ChangeEnvironmentalConditions':{'EnvironmentalConditions':{'AmbientGas':[
        {'Name':name,'Amount':scalar('0To1',value)} for name,value in
        [('Nitrogen',1-oxygen-.0004-co),('Oxygen',oxygen),('CarbonDioxide',.0004),('CarbonMonoxide',co)]]}}}}

def environment_signature(state):
    c=state['Environment']['Common']['EnvironmentalConditions']
    # Exclude calculated air density; retain all actual prescribed conditions.
    result={k:v for k,v in c.items() if k not in ('AirDensity','AmbientGas')}
    result['AmbientGas']={x['Name']:x['Amount']['Scalar0To1'].get('Value',0.0) for x in c['AmbientGas']}
    return result

class _ExposureNative(PulseSession):
    def _requests_json(self):
        p=json.loads(super()._requests_json());p['DataRequest'].extend(q for _,q in EXPOSURE_REQUESTS)
        return json.dumps(p)
    def _read(self):
        self._require_ready();v=self._engine.pull_data()
        if len(v)!=len(self.requested_fields)+len(EXPOSURE_REQUESTS)+1 or not math.isfinite(v[0]) or v[0]<0:
            raise V2Error('NATIVE_DATA_SHAPE','Invalid exposure data')
        return v

class ExposureSession(ResearchPulseSession):
    def __init__(self,patient_id,requested_fields):
        super().__init__(patient_id,requested_fields);self._native=_ExposureNative(patient_id,requested_fields=requested_fields)
    def initialize(self,log_path,configuration=None):
        if configuration is not None:raise V2Error('UNVALIDATED_SCOPE','Fixed StandardMale state only')
        super().initialize(log_path)
        if self._native.get_timestep()!=.02:raise V2Error('UNVALIDATED_TIMESTEP','Only .02s is verified')
    def diagnostics(self):
        v=self._native._read();offset=len(self._native.requested_fields)+1
        return {k:float(x) if math.isfinite(x) else None for (k,_),x in zip(EXPOSURE_REQUESTS,v[offset:])}
    def exposure_observation(self,exposure_id,epoch):
        now=self.get_simulation_time()
        return ExposureObservation(patient_id=self.patient_id,exposure_id=exposure_id,session_epoch=epoch,simulation_time_s=now,
            native_events=self.active_events(),**{k:{'value':v,'status':'available' if v is not None else 'unavailable','observed_at_s':now} for k,v in self.diagnostics().items()})
    def advance_to(self,target):
        now=self.get_simulation_time();ticks=round((target-now)/.02)
        if ticks<0 or abs(now+ticks*.02-target)>1e-6:raise V2Error('INVALID_TIME','Target must align with native ticks')
        for _ in range(ticks):
            if not self._native.advance_step():raise V2Error('NATIVE_ADVANCE_FAILED','Pulse stopped')
    def _restore_control(self,state):
        raise V2Error('UNSUPPORTED_RECOVERY','No public state injection')
    def _fork_pretreatment(self,state,log_path,kind):
        if self._initialized:raise V2Error('ALREADY_INITIALIZED','Cannot replace a live session')
        s=json.loads(state);co,o2,healthy,pre,_=PROFILES[kind]
        if s.get('ActiveActions',{}).get('AnyAction') or s.get('Conditions',{}).get('AnyCondition'):
            raise V2Error('CONTROL_FORK_SCOPE','No other active injuries/equipment')
        if abs(native_scalar(s,'SimulationTime')-healthy-pre)>1e-6:
            raise V2Error('CONTROL_FORK_SCOPE','Only fixed pretreatment instant')
        gases=environment_signature(s)['AmbientGas']
        expected={'Nitrogen':1-o2-.0004-co,'Oxygen':o2,'CarbonDioxide':.0004,'CarbonMonoxide':co}
        if gases.keys()!=expected.keys() or any(abs(gases[k]-v)>1e-12 for k,v in expected.items()):
            raise V2Error('CONTROL_FORK_SCOPE','Unexpected native environment')
        self._initialized=True;self._native._create_engine(log_path)
        self._native.ready=bool(self._native._engine.serialize_from_string(state,self._native._requests_json(),self._native._format))
        if not self._native.ready:raise V2Error('INITIALIZATION_FAILED','Native fork rejected')
        self._native._dt=self._native._engine.get_timestep('s')
        if self._native._dt!=.02:raise V2Error('UNVALIDATED_TIMESTEP','Wrong native timestep')
