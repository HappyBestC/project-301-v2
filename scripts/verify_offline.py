"""Validate the bundled accepted schedule; no API, Pulse or solver."""
import sys, json, copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from core301.dispatch.minimal.api import load_config,load_cases,build_input,read
from core301.dispatch.minimal.models import Schedule
from core301.dispatch.minimal.validation import validate_schedule
source=ROOT/'runs/medical_resources_deepseek_001'
context=read(source/'dispatch_input.json');schedule=read(source/'schedule.json')
frozen=copy.deepcopy(context)
rebuilt=build_input(*load_config(),load_cases(),horizon_min=120,observation_time_min=60)
assert rebuilt==context, 'Bundled data/configuration differs from accepted input'
assert Schedule.model_validate(read(source/'attempt_01/response.txt')).model_dump()==schedule
v=validate_schedule(context,schedule)
assert not v['conflicts'] and v['scheduled_patients']==16 and len(v['unchecked'])==54
assert not v['fully_verified'] and context==frozen
assert v==read(source/'validation.json'), 'Validation replay differs from saved result'
assert v['observation_summary']==read(source/'observation_summary.json')
assert v['planning_summary']==read(source/'planning_summary.json')
assert 'PyPulse' not in sys.modules
print(json.dumps({'input_rebuilt_equal':True,'validation_replay_equal':True,'patients':16,'operations':len(schedule['operations']),'transports':len(schedule['transports']),'care':len(schedule['care']),'conflicts':len(v['conflicts']),'unchecked':len(v['unchecked']),'fully_verified':v['fully_verified'],'source_state_mutated':False,'Pulse_loaded':False},ensure_ascii=False,indent=2))
