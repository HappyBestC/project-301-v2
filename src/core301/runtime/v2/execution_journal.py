"""Durable write-before-submit journal. Native state recovery is deliberately blocked."""
import copy
import json
import os
from pathlib import Path
from uuid import uuid4

from .errors import V2Error


class ExecutionJournal:
    def __init__(self, directory, run_id, patient_id, session_epoch):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/"execution_journal.json"
        self.reopened=self.path.exists()
        if self.reopened:
            self.data=json.loads(self.path.read_text())
            if (self.data["run_id"],self.data["patient_id"])!=(run_id,patient_id):
                raise V2Error("JOURNAL_IDENTITY_MISMATCH", "Journal belongs to another run/patient")
        else:
            self.data={"version":"301.v2.execution.phase1.1","run_id":run_id,"patient_id":patient_id,
                       "session_epoch":session_epoch,"production_enabled":False,"plans":{},"events":[]}
            self.flush()

    def flush(self):
        temporary=self.path.with_suffix(".tmp")
        with temporary.open("w") as stream:
            json.dump(self.data,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.path)
        fd=os.open(self.directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def event(self, request_id, action_id, state, simulation_time_s, **detail):
        self.data["events"].append({"event_id":uuid4().hex,"request_id":request_id,"action_id":action_id,
            "state":state,"simulation_time_s":simulation_time_s,**detail})
        self.flush()

    def query(self, request_id):
        data=json.loads(self.path.read_text()) if self.reopened else self.data
        record=copy.deepcopy(data["plans"].get(request_id))
        if record is not None and self.reopened:
            record["recovery_required"]=True
            for item in record["actions"]:
                if item["submitted_time_s"] is not None and item["lifecycle"] not in ("COMPLETED","STOPPED","NOT_ATTEMPTED"):
                    item["last_saved_state"]=item["state"]
                    item.update(state="UNKNOWN",lifecycle="UNKNOWN")
        return record
