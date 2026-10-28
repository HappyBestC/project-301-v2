"""Spawn-isolated native sessions. No resource ledger or agent in a worker."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import time
from .runner import dump
from core301.pulse.observation_projector import BASIC


class WorkerUncertain(RuntimeError):
    """Transport failure is not evidence of a native rejection."""


def _serve(pipe, run_id, patient_id, fields):
    from core301.pulse.v2.session import ResearchPulseSession
    session=ResearchPulseSession(patient_id,fields)
    allowed={'initialize','advance_time','get_simulation_time','read_requested_data','diagnostics',
             'active_events','serialize_state','execution_state','_submit','close'}
    while True:
        try:cmd=pipe.recv()
        except EOFError:break
        reply={k:cmd[k] for k in ('run_id','patient_id','command_id')}
        reply['worker_pid']=os.getpid()
        try:
            if (cmd['run_id'],cmd['patient_id'])!=(run_id,patient_id) or cmd['operation'] not in allowed:
                raise ValueError('Worker identity/operation mismatch')
            if cmd['operation']=='_submit' and cmd['args'][1]=='treatment':
                binding=cmd.get('execution_identity')
                if not binding or (binding['run_id'],binding['patient_id'])!=(run_id,patient_id):
                    raise ValueError('Treatment lacks bound execution identity')
            actual=session.get_simulation_time() if session.ready else None
            if actual is not None and abs(actual-cmd['expected_time_s'])>1e-6:
                raise ValueError('Worker expected time mismatch')
            value=getattr(session,cmd['operation'])(*cmd['args'])
            reply.update(ok=True,value=value)
        except Exception as exc:
            reply.update(ok=False,error_type=type(exc).__name__,error=str(exc))
        reply.update(ready=session.ready,action_results=session.action_results,
                     simulation_time_s=session.get_simulation_time() if session.ready else None)
        pipe.send(reply)
        if cmd['operation']=='close':break
    session.close();pipe.close()


class PulseWorkerSession:
    native=True
    def __init__(self,run_id,patient_id,directory,fields=BASIC,timeout=60):
        self.run_id,self.patient_id=run_id,patient_id
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.timeout=timeout;self.time=0.;self.ready=False;self.action_results=[]
        self.sequence=0;self.uncertain=False;self.closed=False;self.execution_identity=None
        ctx=mp.get_context('spawn');self.pipe,child=ctx.Pipe()
        self.process=ctx.Process(target=_serve,args=(child,run_id,patient_id,tuple(fields)),daemon=True)
        self.process.start();child.close()
        self.worker_pid=self.process.pid

    def call(self,operation,*args):
        if self.uncertain or self.closed:raise WorkerUncertain('Worker unavailable; no command replay')
        self.sequence+=1
        command=dict(run_id=self.run_id,patient_id=self.patient_id,command_id=self.sequence,
                     expected_time_s=self.time,operation=operation,args=args,execution_identity=self.execution_identity)
        start=time.monotonic();reply=None
        try:
            self.pipe.send(command)
            if not self.pipe.poll(self.timeout):raise TimeoutError('Worker timeout')
            reply=self.pipe.recv()
            if any(reply[k]!=command[k] for k in ('run_id','patient_id','command_id')) or reply['worker_pid']!=self.worker_pid:
                raise ValueError('Worker reply identity mismatch')
            self.action_results=reply['action_results'];self.ready=reply['ready']
            if reply['simulation_time_s'] is not None:self.time=reply['simulation_time_s']
            if not reply['ok']:raise RuntimeError(reply['error_type']+': '+reply['error'])
            return reply['value']
        except Exception as exc:
            self.uncertain=True
            raise WorkerUncertain(str(exc)) from exc
        finally:
            # Native state blobs are saved separately; command identities/times and
            # native action receipts are sufficient for the transport journal.
            event={**{k:v for k,v in command.items() if k!='args'},'worker_pid':self.worker_pid,
                   'wall_elapsed_s':time.monotonic()-start,'ok':reply.get('ok') if reply else None,
                   'reply_time_s':reply.get('simulation_time_s') if reply else None,
                   'uncertain':self.uncertain}
            with (self.directory/'worker_commands.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')

    def bind_execution(self,identity):
        if (identity['run_id'],identity['patient_id'])!=(self.run_id,self.patient_id):
            raise ValueError('Cross-patient execution binding')
        if self.execution_identity is not None and identity!=self.execution_identity:
            raise ValueError('Execution binding cannot change')
        self.execution_identity=dict(identity)

    def initialize(self,path,configuration=None):return self.call('initialize',str(path),configuration)
    def advance_time(self,seconds):return self.call('advance_time',seconds)
    def get_simulation_time(self):return self.call('get_simulation_time')
    def read_requested_data(self):return self.call('read_requested_data')
    def diagnostics(self):return self.call('diagnostics')
    def active_events(self):return self.call('active_events')
    def serialize_state(self):return self.call('serialize_state')
    def execution_state(self):return self.call('execution_state')
    def _submit(self,payload,phase):return self.call('_submit',payload,phase)
    def close(self):
        if self.closed:return
        try:
            if not self.uncertain and self.process.is_alive():self.call('close')
        finally:
            self.process.join(timeout=2)
            if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
            self.pipe.close();self.ready=False;self.closed=True
