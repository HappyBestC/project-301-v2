"""Load the existing male initial state and read observations; no treatment or advance."""
from pathlib import Path
import json,tempfile
from core301.pulse.session import PulseSession
import PyPulse
with tempfile.TemporaryDirectory(prefix='301-research-smoke-') as d:
    s=PulseSession('research-cleanup-smoke')
    try:
        s.initialize(Path(d)/'pulse.log')
        fields=list(s.read_requested_data())
        assert len(fields)==5 and s.get_simulation_time()==0
        print(json.dumps({'pulse_module':PyPulse.__file__,'time_s':0,'fields':fields,'treatment_actions':0,'advanced_steps':0}))
    finally:s.close()
