"""Read native devices; action acceptance alone does not confirm execution."""
from core301.pulse.v2.session import native_scalar
from core301.runtime.v2.errors import V2Error

def validate_devices(state,executed,now,decision):
 actions={}
 for wrapper in state.get('ActiveActions',{}).get('AnyAction',[]):
  for category in wrapper.values():
   for name,body in category.items():actions.setdefault(name,[]).append(body)
 mapping={'occlusive_dressing':'ChestOcclusiveDressing','needle_decompression':'NeedleDecompression','intubation':'Intubation','mechanical_ventilation':'MechanicalVentilatorPressureControl','supplemental_oxygen':'SupplementalOxygen','fluid_resuscitation':'SubstanceCompoundInfusion','chest_tube':'TubeThoracostomy'}
 def fail():raise V2Error('NATIVE_DEVICE_MISMATCH','Unexpected/missing/modified native device or delivery parameters')
 for kind,name in mapping.items():
  bodies=actions.get(name,[])
  if kind not in executed:
   if bodies:fail()
   continue
  if len(bodies)!=1:
   # Source-controlled chest drainage and finite bag can legitimately auto-stop.
   if kind in ('chest_tube','fluid_resuscitation') and not bodies and now>decision+1:continue
   fail()
  b=bodies[0]
  if kind in ('occlusive_dressing','needle_decompression') and (b.get('Side')!='Left' or b.get('State')!='On'):fail()
  if kind=='intubation' and (b.get('Type')!='Tracheal' or state.get('Intubation')!='On'):fail()
  if kind=='chest_tube' and (b.get('Side')!='Left' or native_scalar(b,'FlowRate')!=30):fail()
  if kind=='fluid_resuscitation' and (b.get('SubstanceCompound')!='Saline' or native_scalar(b,'Rate')!=100 or not 0<=native_scalar(b,'BagVolume')<=500):fail()
  if kind=='supplemental_oxygen' and (b.get('Device')!='NasalCannula' or native_scalar(b,'Flow')!=.5 or not 0<native_scalar(b,'Volume')<=425 or state.get('AirwayMode')!='NasalCannula'):fail()
  if kind=='mechanical_ventilation':
   for key,value in {'FractionInspiredOxygen':.21,'InspiratoryPeriod':1,'InspiratoryPressure':13,'PositiveEndExpiratoryPressure':5,'RespirationRate':12,'Slope':.1}.items():
    if native_scalar(b,key)!=value:fail()
   if state.get('AirwayMode')!='MechanicalVentilator' or b.get('MechanicalVentilatorMode',{}).get('Connection')!='On':fail()
 return {'native_devices_confirmed':True,'executed':list(executed),'time_s':now}
