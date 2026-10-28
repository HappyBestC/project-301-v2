"""Restricted phase-1 execution, hand plans only; production defaults to refusal."""
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from pydantic import ValidationError

from core301.contracts.context import ResourceState
from core301.contracts.casualty import TEMPLATES
from core301.contracts.v2.context import AgentCaseContext
from core301.contracts.v2.injury import CasualtyInput
from core301.contracts.v2.treatment import TreatmentPlan, action_identity
from core301.pulse.observation_projector import BASIC, ObservationAccess, ObservationProjector
from core301.pulse.v2.injury_adapter import InjuryAdapter, PatientInitializer
from core301.pulse.v2.protocol_book import PROFILE_VERSION, validate_injury_scope
from core301.pulse.v2.session import ResearchPulseSession, native_scalar
from core301.pulse.v2.treatment_adapter import TreatmentAdapter
from .capability import validate_capability
from .errors import V2Error
from .execution_journal import ExecutionJournal
from .injury_registry import InjuryRegistry


@dataclass(frozen=True)
class DecisionContext:
    context_ref: str
    public: AgentCaseContext


class CaseRuntime:
    def __init__(self, patient_id, directory, *, run_id, mode="production", resources=None, access=None, session=None):
        if mode not in ("research","production"):
            raise ValueError("Explicit research or production mode required")
        if not isinstance(patient_id,str) or not patient_id.strip() or not isinstance(run_id,str) or not run_id.strip():
            raise ValueError("Nonblank run_id/patient_id required")
        self.patient_id=patient_id;self.run_id=run_id;self.mode=mode
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.session_epoch=uuid4().hex
        self.access=access or ObservationAccess()
        self.session=session or ResearchPulseSession(patient_id,(*BASIC,*sorted(self.access.visible())))
        if self.session.patient_id!=patient_id:
            raise V2Error("PATIENT_MISMATCH","Session patient mismatch")
        self.resources=resources
        self.registry=InjuryRegistry(patient_id)
        self.journal=ExecutionJournal(self.directory,run_id,patient_id,self.session_epoch)
        self._contexts={};self._effects={};self._delivery_removals={};self._prepared=False;self._halted=False;self._closed=False
        self._control_only=False;self._lock=RLock();self.casualty=None

    def _write(self, name, value):
        (self.directory/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

    def prepare(self, casualty):
        with self._lock:
            if self.mode!="research":
                raise V2Error("PRODUCTION_NOT_ENABLED","Phase 1 has no production-enabled patient/protocol route")
            if self.journal.reopened:
                raise V2Error("RESTART_REQUIRES_RECOVERY","Existing journal can be queried; native recovery is not implemented")
            if self._prepared or self._closed:
                raise V2Error("ALREADY_PREPARED","Use a new runtime for a new injury episode")
            try:
                casualty=CasualtyInput.model_validate(casualty)
            except ValidationError as exc:
                raise V2Error("INVALID_INJURY_SCHEMA",str(exc)) from exc
            if casualty.patient_id!=self.patient_id:
                raise V2Error("PATIENT_MISMATCH","Input patient mismatch")
            injury=validate_injury_scope(casualty)
            self.casualty=CasualtyInput.model_validate(casualty.model_dump())
            self._write("injury_input.json",self.casualty.model_dump())
            config=PatientInitializer().configuration(casualty) if casualty.conditions else None
            self._write("initialization.json",{"mode":"Condition" if config else "verified_healthy_state",
                "configuration":config,"patient":"StandardMale","pulse_version":"4.3.2",
                "healthy_or_condition_elapsed_s":60,"injury_elapsed_s":120,"condition_exists_since_initialization":bool(config)})
            try:
                self.session.initialize(self.directory/"pulse.log",config)
                self.session.advance_time(60)
                for dynamic in casualty.dynamic_injuries:
                    self.session._submit(InjuryAdapter().convert_dynamic(dynamic),"injury")
                self.session.advance_time(120)
                self.registry.register(casualty)
                self._prepared=True
                self._write("initialization_result.json",{"accepted":True,"simulation_time_s":self.session.get_simulation_time(),
                    "injury_records":self.session.action_results,"condition_accepted_at_initialization":bool(config)})
            except Exception as exc:
                self._halted=True
                self._write("initialization_result.json",{"accepted":False,"error":str(exc),"injury_records":self.session.action_results})
                raise V2Error("INITIALIZATION_FAILED",str(exc)) from exc
            return self.observe()

    def observe(self):
        return ObservationProjector().project(self.patient_id,self.session.get_simulation_time(),self.session.read_requested_data(),self.access)

    def build_context(self, *, authorized_locations=None):
        with self._lock:
            if not self._prepared:raise V2Error("NOT_PREPARED","Initialize the verified patient first")
            known=self.registry.known()
            if authorized_locations is not None:
                known=[x for x in known if x.get("side",x.get("compartment",x["injury_type"])) in authorized_locations]
            snapshot=(self.resources.snapshot(self.run_id,self.patient_id) if self.resources is not None else
                      ResourceState(**{k:0 for k in ResourceState.model_fields}))
            public=AgentCaseContext(patient_id=self.patient_id,known_injuries=known,patient_observation=self.observe(),available_resources=snapshot)
            ref=uuid4().hex
            # Store an owned backend copy; mutations to a provider copy cannot grant rights.
            self._contexts[ref]=(public.model_dump(exclude_unset=True),self.registry.signature())
            return DecisionContext(ref,AgentCaseContext.model_validate(public.model_dump(exclude_unset=True)))

    def query(self, request_id):
        with self._lock:return self.journal.query(request_id)

    def _validate_native_sources(self, state, source):
        """Reject backend/native drift, including an unregistered second source."""
        injury_names={x["pulse_action"] for x in TEMPLATES.values()} | {"ImpairedAlveolarExchangeExacerbation"}
        keys=[]
        for name,bodies in state["actions"].items():
            if name not in injury_names:continue
            for body in bodies:
                if name=="Hemorrhage":key=(name,body.get("Compartment"))
                elif name=="TensionPneumothorax":key=(name,body.get("Side"),body.get("Type","Open"))
                elif name=="Hemothorax":key=(name,body.get("Side"))
                else:key=(name,)
                keys.append(key)
        expected=[] if source.injury_type=="dehydration" or source.controlled else [source.native_key]
        if keys!=expected:
            raise V2Error("UNREGISTERED_NATIVE_SOURCE","Native injury identities differ from the trusted single-source registry")
        if source.injury_type in ("external_hemorrhage","abdominal_internal_hemorrhage") and not source.controlled:
            body=state["actions"]["Hemorrhage"][0]
            expected_type="External" if source.injury_type=="external_hemorrhage" else "Internal"
            if body.get("Type","External")!=expected_type or native_scalar(body,"Severity")!=source.initial_severity:
                raise V2Error("STALE_NATIVE_SOURCE","Native bleed type/severity differs from the registered source")

    def validate_treatment_timing(self, plan, source, now):
        """Default frozen protocol. Separate research subclasses may narrow scope."""
        if abs(now-180)>1e-6:
            raise V2Error("UNVALIDATED_TIMING","Phase-1 treatment begins at the verified 180s decision point")
        return None

    def execute_plan(self, plan, *, request_id, context_ref):
        with self._lock:
            if not isinstance(request_id,str) or not request_id.strip():
                raise V2Error("INVALID_REQUEST_ID","A backend request identity is mandatory")
            try:
                plan=TreatmentPlan.model_validate(plan)
            except ValidationError as exc:
                raise V2Error("INVALID_TREATMENT_SCHEMA",str(exc)) from exc
            plan=TreatmentPlan.model_validate(plan.model_dump())
            digest=hashlib.sha256(json.dumps(plan.model_dump(),sort_keys=True).encode()).hexdigest()
            previous=self.journal.query(request_id)
            if previous is not None:
                if previous["plan_sha256"]!=digest or previous["context_ref"]!=context_ref:
                    raise V2Error("IDEMPOTENCY_CONFLICT","Request ID cannot be reused with another plan/context")
                return previous  # includes pending/unknown/failure; never resubmit
            if self.journal.reopened:
                raise V2Error("RESTART_REQUIRES_RECOVERY","New requests blocked after process restart")
            if not self._prepared or self._closed:raise V2Error("NOT_PREPARED","No active V2 patient")
            if self._halted:raise V2Error("EXECUTION_HALTED","Prior execution uncertainty/failure blocks new requests")
            if context_ref not in self._contexts:raise V2Error("CONTEXT_NOT_FOUND","Context belongs to another run/epoch or was not issued")
            context_data,signature=self._contexts[context_ref]
            public=AgentCaseContext.model_validate(context_data)
            now=self.session.get_simulation_time()
            plan_id=uuid4().hex
            record={"plan_id":plan_id,"request_id":request_id,"patient_id":self.patient_id,"run_id":self.run_id,
                "session_epoch":self.session_epoch,"context_ref":context_ref,"plan_sha256":digest,"plan":plan.model_dump(),
                "protocol_version":PROFILE_VERSION,"production_enabled":False,"status":"PROPOSED","actions":[],"error":None}
            for index,action in enumerate(plan.actions):
                record["actions"].append({"action_id":uuid4().hex,"action_index":index,"action_type":action.action_type,
                    "business_action":action.model_dump(),"target":None,"protocol_id":None,"native_payload":None,
                    "proposed_time_s":now,"submitted_time_s":None,"accepted":None,"state":"PROPOSED","lifecycle":"PLANNED",
                    "native_result":None,"error":None,"validation":None,"resource":None,"device_state":None,
                    "physiological_response":"NOT_EVALUATED","evaluation":"NOT_RUN"})
            self.journal.data["plans"][request_id]=record
            self.journal.event(request_id,None,"PROPOSED",now)
            for item in record["actions"]:
                self.journal.event(request_id,item["action_id"],"PROPOSED",now)
            try:
                source,protocols,_=validate_capability(plan,public,self.registry,signature,self.mode,self.resources)
                if self._control_only and plan.actions:
                    raise V2Error("CONTROL_BRANCH_ONLY","Matched control fork does not accept treatment")
                all_noop=bool(plan.actions)
                for action,item in zip(plan.actions,record["actions"]):
                    key=(action_identity(action),source.injury_id,source.source_version)
                    prior=self._effects.get(key)
                    is_noop=bool(action.action_type.startswith("control_") and source.controlled and prior and prior["lifecycle"]=="COMPLETED")
                    if prior and not is_noop:
                        raise V2Error("ACTION_REPLAY_BLOCKED","Action already submitted or unresolved; query its original request")
                    all_noop &= is_noop
                    item["already_applied_noop"]=is_noop
                if plan.actions and not all_noop:
                    timing=self.validate_treatment_timing(plan,source,now)
                    if timing is not None:
                        record["timing_protocol"]=timing
                        record["protocol_version"]=timing["protocol_version"]
                state=self.session.execution_state()
                self._validate_native_sources(state,source)
                if not all_noop:
                    if state["airway_mode"]!="Free" or state["intubation"]!="Off":
                        raise V2Error("DEVICE_CONFLICT","Unverified existing respiratory device state")
                    if state["actions"].get("SubstanceCompoundInfusion"):
                        raise V2Error("INFUSION_CONFLICT","Cannot allocate a new bag during an existing infusion")
                for item,profile in zip(record["actions"],protocols):
                    item.update(target=source.target(),protocol_id=profile,validation={"schema":"passed","source":"passed","scope":"passed","resource":"pending"})
                executable=[a for a,item in zip(plan.actions,record["actions"]) if not item["already_applied_noop"]]
                if executable:
                    reservation=self.resources.reserve(plan_id,TreatmentPlan(patient_id=self.patient_id,actions=executable),self.run_id,self.patient_id)
                    record["resource_reservation"]=reservation
                for item in record["actions"]:
                    item.update(state="VALIDATED")
                    item["validation"]["resource"]="verified_noop" if item["already_applied_noop"] else "reserved"
                    self.journal.event(request_id,item["action_id"],"VALIDATED",now)
                for action,item in zip(plan.actions,record["actions"]):
                    if self.registry.signature()!=signature:
                        raise V2Error("STALE_SOURCE","Source/version/authorization changed during plan execution")
                    if item["already_applied_noop"]:
                        item.update(state="COMPLETED",lifecycle="COMPLETED",accepted=None,resource={"allocated_units":{},"reason":"verified_same_source_noop"})
                        self.journal.event(request_id,item["action_id"],"COMPLETED",now,reason="already_applied_noop")
                        continue
                    if action.action_type=="mechanical_ventilation" and not any(
                        r["action_type"]=="intubation" and r["accepted"] is True for r in record["actions"][:item["action_index"]]):
                        raise V2Error("DEPENDENCY_FAILED","Intubation was not accepted; no ventilator submission")
                    item["resource"]=self.resources.begin(plan_id,item["action_id"],action.action_type)
                    item["validation"]["resource"]="passed"
                    payload=TreatmentAdapter().convert(action,source,item["protocol_id"])
                    item.update(native_payload=payload,submitted_time_s=self.session.get_simulation_time(),state="SUBMITTED",lifecycle="PENDING_NATIVE_RESULT")
                    key=(action_identity(action),source.injury_id,source.source_version)
                    self._effects[key]=item
                    self.journal.event(request_id,item["action_id"],"SUBMITTED",item["submitted_time_s"])
                    count=len(self.session.action_results)
                    try:
                        native=self.session._submit(payload,"treatment")
                        item.update(accepted=native["accepted"],native_result=native,state="ACCEPTED",lifecycle="PENDING_ADVANCE")
                        self.resources.acknowledge(plan_id,item["action_id"],True)
                        item["resource"].update(submission_status="accepted",delivery_status="pending_advance")
                        self.journal.event(request_id,item["action_id"],"ACCEPTED",item["submitted_time_s"])
                    except Exception as exc:
                        native=self.session.action_results[-1] if len(self.session.action_results)>count else None
                        item.update(accepted=native.get("accepted") if native else None,native_result=native,
                                    state="REJECTED" if native and native.get("accepted") is False else "UNKNOWN",lifecycle="UNKNOWN")
                        self.resources.acknowledge(plan_id,item["action_id"],item["accepted"])
                        item["resource"].update(submission_status="quarantined",delivery_status="unknown")
                        self.journal.event(request_id,item["action_id"],item["state"],item["submitted_time_s"],error=str(exc))
                        raise V2Error("NATIVE_REJECTED" if item["accepted"] is False else "SUBMISSION_UNKNOWN",str(exc)) from exc
                if self.registry.signature()!=signature:
                    raise V2Error("STALE_SOURCE","Source/version/authorization changed before plan completion")
                record["status"]="ACCEPTED_PENDING_ADVANCE" if executable else "COMPLETED" if plan.actions else "VALIDATED_EMPTY_PLAN"
                self.journal.flush()
            except Exception as exc:
                code=exc.code if isinstance(exc,V2Error) else "EXECUTION_FAILED"
                submitted=any(x["submitted_time_s"] is not None for x in record["actions"])
                record.update(status="FAILED_PARTIAL" if submitted else "REJECTED_BEFORE_EXECUTION",error={"code":code,"message":str(exc)})
                for item in record["actions"]:
                    if item["accepted"] is not True and item["state"] not in ("REJECTED","UNKNOWN"):
                        item.update(state="FAILED",lifecycle="NOT_ATTEMPTED",error={"code":code,"message":str(exc)})
                if submitted:self._halted=True
                if self.resources is not None and submitted:self.resources.release_unused(plan_id)
                self.journal.event(request_id,None,"FAILED",now,error=record["error"])
                raise V2Error(code,str(exc)) from exc
            return self.query(request_id)

    def advance(self, seconds, *, reconcile=True):
        with self._lock:
            if not self._prepared:raise V2Error("NOT_PREPARED","Initialize the verified patient first")
            if self._closed:raise V2Error("SESSION_CLOSED","Cannot advance a closed patient")
            if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:
                raise V2Error("INVALID_ADVANCE_ARGUMENT","Advance duration must be finite and nonnegative")
            # Watch the final possible bag interval, not a wall-clock completion
            # timer. Completed requires witnessed native removal at the fixed rate.
            final_candidates=[]
            before_time=self.session.get_simulation_time()
            if before_time+seconds>480+1e-6:
                raise V2Error("UNVALIDATED_WINDOW","Phase-1 research response is bounded to 300s after the 180s decision")
            if type(seconds) in (int,float) and seconds>=0:
                for record in self.journal.data["plans"].values():
                    for item in record["actions"]:
                        if item["accepted"] is True and item["action_type"] in ("fluid_resuscitation","transfusion") and item["lifecycle"]!="COMPLETED" and before_time+seconds-item["submitted_time_s"]>=300-1e-6:
                            final_candidates.append(item)
            final_before=self.session.execution_state() if final_candidates else None
            try:
                self.session.advance_time(seconds)
            except Exception as exc:
                self._halted=True
                for record in self.journal.data["plans"].values():
                    for item in record["actions"]:
                        if item["accepted"] is True and item["lifecycle"] not in ("COMPLETED","STOPPED"):
                            item.update(state="FAILED",lifecycle="UNKNOWN",error={"code":"ADVANCE_FAILED","message":str(exc)})
                self.journal.event(None,None,"FAILED",None,error={"code":"ADVANCE_FAILED","message":str(exc)})
                raise V2Error("ADVANCE_FAILED",str(exc)) from exc
            if final_candidates:
                final_after=self.session.execution_state()
                actual_elapsed=self.session.get_simulation_time()-before_time
                for item in final_candidates:
                    compound="Saline" if item["action_type"]=="fluid_resuscitation" else "Blood"
                    preceding=[b for b in final_before["actions"].get("SubstanceCompoundInfusion",[]) if b.get("SubstanceCompound")==compound]
                    following=[b for b in final_after["actions"].get("SubstanceCompoundInfusion",[]) if b.get("SubstanceCompound")==compound]
                    previous_volume=native_scalar(preceding[0],"BagVolume") if len(preceding)==1 else None
                    previous_rate=native_scalar(preceding[0],"Rate") if len(preceding)==1 else None
                    if not following and previous_volume is not None and previous_rate==100 and previous_volume<=actual_elapsed*100/60+1e-7:
                        self._delivery_removals[item["action_id"]]={"completion_evidence":"witnessed native active bag then removal during uninterrupted fixed-rate advance",
                            "previous_remaining_bag_mL":previous_volume,"advance_interval_s":actual_elapsed,"native_action_removed":True,
                            "dose_mass_exactly_500mL_claimed":False}
            if reconcile:self._reconcile()
            return self.observe()

    def _reconcile(self):
        state=self.session.execution_state();now=self.session.get_simulation_time()
        for request,record in self.journal.data["plans"].items():
            for item in record["actions"]:
                if item["accepted"] is not True or item["lifecycle"] in ("COMPLETED","STOPPED"):
                    continue
                kind=item["action_type"];previous=item["lifecycle"]
                item["device_state"]={"observed_at_s":now,"airway_mode":state["airway_mode"],"intubation":state["intubation"]}
                lifecycle="UNKNOWN";detail={}
                if kind.startswith("control_"):
                    remaining=[h for h in state["actions"].get("Hemorrhage",[]) if h.get("Compartment")==item["target"].get("compartment")]
                    target_valid=any(s.injury_id==item["target"]["injury_id"] and s.source_version==item["target"]["source_version"] and s.active and s.authorized for s in self.registry.sources())
                    if not target_valid:
                        detail={"confirmation_error":"STALE_SOURCE","native_result_preserved":True}
                    elif not remaining and state["diagnostics"].get("diagnostic.TotalHemorrhageRate")==0:
                        lifecycle="COMPLETED"
                        self.registry.mark_controlled(item["target"]["injury_id"],item["target"]["source_version"])
                        detail={"source_control_confirmed":True,"cumulative_loss_mL":state["diagnostics"].get("diagnostic.TotalHemorrhagedVolume"),"capacity_restoration_claimed":False}
                elif kind in ("fluid_resuscitation","transfusion"):
                    compound="Saline" if kind=="fluid_resuscitation" else "Blood"
                    matches=[b for b in state["actions"].get("SubstanceCompoundInfusion",[]) if b.get("SubstanceCompound")==compound]
                    remaining=native_scalar(matches[0],"BagVolume") if len(matches)==1 else None
                    if remaining is not None:
                        lifecycle="ACTIVE" if remaining>0 else "COMPLETED"
                        detail={"remaining_bag_mL":remaining,"nominal_initial_bag_mL":500,"delivered_mL":500-remaining}
                    elif item["action_id"] in self._delivery_removals:
                        lifecycle="COMPLETED";detail=self._delivery_removals[item["action_id"]]
                elif kind=="supplemental_oxygen":
                    matches=state["actions"].get("SupplementalOxygen",[])
                    if len(matches)==1 and matches[0].get("Device")=="NasalCannula":
                        lifecycle="ACTIVE";detail={"remaining_oxygen_L":native_scalar(matches[0],"Volume"),"device":"NasalCannula","flow_L_min":0.5}
                elif kind=="intubation":
                    if state["intubation"]=="On":lifecycle="COMPLETED"
                elif kind=="mechanical_ventilation":
                    if state["airway_mode"]=="MechanicalVentilator":lifecycle="ACTIVE"
                elif kind in ("occlusive_dressing","needle_decompression"):
                    native_name="ChestOcclusiveDressing" if kind=="occlusive_dressing" else "NeedleDecompression"
                    if any(b.get("Side")==item["target"].get("side") and b.get("State")=="On" for b in state["actions"].get(native_name,[])):
                        lifecycle="ACTIVE"
                item.update(state=lifecycle,lifecycle=lifecycle,delivery=detail,last_verified_time_s=now)
                if item["resource"] is not None:
                    item["resource"].update(delivery_status=lifecycle.lower(),native_delivery_evidence=detail)
                if previous!=lifecycle:self.journal.event(request,item["action_id"],lifecycle,now)
            if record["status"] not in ("FAILED_PARTIAL","REJECTED_BEFORE_EXECUTION","VALIDATED_EMPTY_PLAN"):
                record["status"]="COMPLETED" if all(x["lifecycle"]=="COMPLETED" for x in record["actions"]) else "ACTIVE" if any(x["lifecycle"]=="ACTIVE" for x in record["actions"]) else "UNKNOWN"
        self.journal.flush()

    def fork_control(self, directory, *, run_id):
        """Matched, treatment-disabled control of this verified pretreatment state."""
        with self._lock:
            if self.mode!="research" or not self._prepared or self.journal.data["plans"] or abs(self.session.get_simulation_time()-180)>1e-6:
                raise V2Error("CONTROL_FORK_SCOPE","Fork only the verified pretreatment patient")
            clone=CaseRuntime(self.patient_id,directory,run_id=run_id,mode="research",access=self.access)
            clone.session._restore_control(self.session.serialize_state())
            clone.casualty=CasualtyInput.model_validate(self.casualty.model_dump())
            clone.registry.register(clone.casualty)
            clone._prepared=True;clone._control_only=True
            clone._write("control_origin.json",{"origin_run_id":self.run_id,"matched_state_sha256":hashlib.sha256(self.session.serialize_state().encode()).hexdigest(),"treatment_disabled":True})
            return clone

    def close(self):
        with self._lock:
            if self._closed:return
            time=self.session.get_simulation_time() if self.session.ready else None
            for request,record in self.journal.data["plans"].items():
                for item in record["actions"]:
                    if item["lifecycle"] in ("ACTIVE","PENDING_ADVANCE"):
                        item.update(state="STOPPED",lifecycle="STOPPED",stop_reason="research_case_closed_not_treatment_goal")
                        self.journal.event(request,item["action_id"],"STOPPED",time)
            self.session.close();self._closed=True
            if self.resources is not None:
                self._write("resource_audit_before_close.json",self.resources.audit())
                self.resources.close_case()
