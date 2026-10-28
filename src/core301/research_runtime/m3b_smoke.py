"""Real isolated-worker qualification, no treatment or resource allocation."""
import argparse
import hashlib
import json
from uuid import uuid4
from core301.paths import PROJECT_ROOT
from core301.contracts.v2.injury import CasualtyInput
from core301.pulse.v2.injury_adapter import InjuryAdapter
from core301.pulse.v2.protocol_book import validate_injury_scope
from .pulse_worker import PulseWorkerSession
from .runner import dump
from .evaluation import sha


def casualty(patient_id):
    case=CasualtyInput.model_validate({'patient_id':patient_id,'injuries':[
        {'injury_type':'external_hemorrhage','compartment':'RightLeg','severity':.4}]})
    validate_injury_scope(case)
    return case


def smoke(run_id=None):
    run_id=run_id or 'isolation-'+uuid4().hex
    if '/' in run_id or run_id in ('.','..'):raise ValueError('Invalid run id')
    directory=PROJECT_ROOT/'experiments/results/m3b_dual_patient'/run_id
    directory.mkdir(parents=True,exist_ok=False);sessions={};report={'run_id':run_id,'mode':'native_isolation_smoke','status':'BLOCKED'}
    try:
        for label in ('A','B'):
            s=PulseWorkerSession(run_id,run_id+'-'+label,directory/label);sessions[label]=s
            s.initialize(directory/label/'pulse.log')
        a,b=sessions.values()
        assert a.worker_pid!=b.worker_pid
        before=json.loads(b.serialize_state());dump(directory/'B/before_A_change.json',before);a.advance_time(60.)
        case=casualty(a.patient_id)
        a._submit(InjuryAdapter().convert_dynamic(case.dynamic_injuries[0]),'injury')
        b_time=b.get_simulation_time();after=json.loads(b.serialize_state());dump(directory/'B/after_A_change.json',after)
        assert abs(b_time)<1e-6, f'B advanced unexpectedly: {b_time}'
        assert after==before, 'B semantic serialized state changed while only A advanced'
        assert a.execution_state()['actions'].get('Hemorrhage') and not b.execution_state()['actions'].get('Hemorrhage')
        report['A_change_B_unchanged']=True
        b.advance_time(60.);case=casualty(b.patient_id)
        b._submit(InjuryAdapter().convert_dynamic(case.dynamic_injuries[0]),'injury')
        for s in sessions.values():s.advance_time(120.)
        times={k:s.get_simulation_time() for k,s in sessions.items()}
        assert all(abs(t-180)<1e-6 for t in times.values())
        for k,s in sessions.items():
            dump(directory/k/'observation.json',{'patient_id':s.patient_id,'time_s':s.get_simulation_time(),
                'measurements':{key:vars(value) for key,value in s.read_requested_data().items()}})
            (directory/k/'state.json').write_text(s.serialize_state())
        a.close();b.advance_time(1.)
        assert abs(b.get_simulation_time()-181)<1e-6 and b.ready
        report.update(status='PASS',worker_pids={k:s.worker_pid for k,s in sessions.items()},
            synchronized_times=times,close_A_B_still_running=True,B_after_close_time_s=b.get_simulation_time(),
            native_treatment_count=0,limitation='Same verified baseline in two isolated processes; not distinct human models')
    except Exception as exc:report['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        for s in sessions.values():s.close()
        dump(directory/'run_summary.json',report)
        dump(directory/'sha256_manifest.json',{str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file() and p.name!='sha256_manifest.json'})
    return directory,report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-id');args=p.parse_args()
    d,r=smoke(args.run_id);print(json.dumps({'directory':str(d),**r},indent=2));raise SystemExit(0 if r['status']=='PASS' else 1)
