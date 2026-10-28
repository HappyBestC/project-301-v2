import copy
import json

import pytest

from core301.agent.v2.manual_provider import ManualTreatmentProvider
from core301.contracts.treatment import TreatmentPlan as V1Plan
from core301.contracts.v2.injury import CasualtyInput
from core301.pulse.observation_projector import BASIC, REQUESTS, ObservationAccess, Sample
from core301.pulse.v2.proxy_adapter import ProxyAdapter
from core301.contracts.v2.treatment import TreatmentPlan
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.injury_registry import InjuryRegistry
from core301.runtime.v2.resources import explicit_test_resources, ResearchResourceFixture


def injury(kind="external_hemorrhage",severity=0.4):
    item={"injury_type":kind,"severity":severity}
    if kind=="external_hemorrhage":item["compartment"]="RightLeg"
    if kind=="abdominal_internal_hemorrhage":item["compartment"]="Spleen"
    return {"patient_id":"P","injuries":[item]}


def proxy_plan(kind="control_external_bleeding"):
    return {"patient_id":"P","actions":[{"action_type":kind,"compartment":"Spleen" if kind=="control_internal_bleeding" else "RightLeg"}]}


class SessionFaultFixture:
    """Fault injection only. No physiological claim is supported by this class."""
    patient_id="P"
    ready=True
    def __init__(self):
        self.time=0.;self.action_results=[];self.fail_at=None;self.unknown_at=None
        self.after_submit=None;self.treatments=0;self.controlled=False;self.state_actions={}
    def initialize(self, log_path, configuration=None):pass
    def advance_time(self,s):self.time+=s
    def get_simulation_time(self):return self.time
    def read_requested_data(self):return {k:Sample(1.,self.time) for k in REQUESTS if not k.startswith("neurologic.")}
    def execution_state(self):
        return {"airway_mode":"Free","intubation":"Off","actions":self.state_actions,
                "diagnostics":{"diagnostic.TotalHemorrhageRate":0. if self.controlled else 1.,"diagnostic.TotalHemorrhagedVolume":42.}}
    def _submit(self,payload,phase):
        if phase=="treatment":
            self.treatments+=1
            if self.treatments==self.unknown_at:raise RuntimeError("network interruption after ambiguous submission")
            accepted=self.treatments!=self.fail_at
        else:accepted=True
        record={"phase":phase,"accepted":accepted,"simulation_time_s":self.time}
        self.action_results.append(record)
        if not accepted:self.ready=False;raise RuntimeError("injected native false")
        if phase=="injury":
            for name,body in payload["PatientAction"].items():self.state_actions[name]=[copy.deepcopy(body)]
        if phase=="treatment":
            if "Hemorrhage" in payload.get("PatientAction",{}):self.controlled=True;self.state_actions.pop("Hemorrhage",None)
            if self.after_submit:self.after_submit(self.treatments)
        return record
    def close(self):self.ready=False


def runtime(tmp_path,session=None,resources="fixture",case=None):
    session=session or SessionFaultFixture()
    resource=explicit_test_resources("r","P") if resources=="fixture" else resources
    grants=frozenset(k for k in REQUESTS if k not in BASIC and not k.startswith("neurologic."))
    rt=CaseRuntime("P",tmp_path,run_id="r",mode="research",resources=resource,session=session,access=ObservationAccess(grants,grants,grants))
    rt.prepare(case or injury())
    return rt


def execute(rt,plan=None,request="request",ticket=None):
    ticket=ticket or rt.build_context()
    return rt.execute_plan(plan or proxy_plan(),request_id=request,context_ref=ticket.context_ref)


def assert_code(code,fn):
    with pytest.raises(V2Error) as result:fn()
    assert result.value.code==code


def test_context_has_resources_but_no_hidden_severity_or_backend_identity(tmp_path):
    rt=runtime(tmp_path);ticket=rt.build_context()
    text=ticket.public.model_dump_json()
    assert "severity" not in text and "injury_id" not in text and "protocol" not in text
    assert ticket.public.available_resources.medic==1
    assert ManualTreatmentProvider(proxy_plan()).create_plan(ticket.public).actions


@pytest.mark.parametrize("kind",["control_external_bleeding","control_internal_bleeding"])
def test_proxy_uses_trusted_source_and_constant_zero(tmp_path,kind):
    case=injury("abdominal_internal_hemorrhage" if kind.endswith("internal_bleeding") else "external_hemorrhage")
    rt=runtime(tmp_path,case=case)
    result=execute(rt,proxy_plan(kind))
    native=result["actions"][0]["native_payload"]["PatientAction"]["Hemorrhage"]
    assert native["Severity"]["Scalar0To1"]["Value"]==0
    assert native["Compartment"]==case["injuries"][0]["compartment"]
    assert result["actions"][0]["target"]["injury_id"]==rt.registry.sources()[0].injury_id
    assert result["actions"][0]["state"]=="ACCEPTED" and result["actions"][0]["lifecycle"]!="COMPLETED"
    assert result["actions"][0]["resource"]["submission_status"]=="accepted"


def test_same_request_returns_record_without_repeat_or_resource_use(tmp_path):
    rt=runtime(tmp_path);ticket=rt.build_context()
    first=execute(rt,ticket=ticket);resource=copy.deepcopy(rt.resources.audit())
    second=execute(rt,ticket=ticket)
    assert first==second and rt.session.treatments==1
    assert rt.resources.audit()==resource
    assert rt.query("request")==first


def test_control_new_request_noop_only_after_confirmed_advance(tmp_path):
    rt=runtime(tmp_path);execute(rt);rt.advance(1)
    stock=copy.deepcopy(rt.resources.audit())
    result=execute(rt,request="new")
    assert result["actions"][0]["already_applied_noop"]
    assert result["actions"][0]["accepted"] is None and rt.session.treatments==1
    assert rt.resources.audit()==stock
    assert rt.query("request")["actions"][0]["resource"]["delivery_status"]=="completed"


def test_pending_control_cannot_be_replayed_with_new_id(tmp_path):
    rt=runtime(tmp_path);execute(rt)
    assert_code("ACTION_REPLAY_BLOCKED",lambda:execute(rt,request="new"))
    assert rt.session.treatments==1


def test_identity_conflict_does_not_resubmit(tmp_path):
    rt=runtime(tmp_path);ticket=rt.build_context();execute(rt,ticket=ticket)
    p={"patient_id":"P","actions":[{"action_type":"transfusion"}]}
    assert_code("IDEMPOTENCY_CONFLICT",lambda:execute(rt,p,ticket=ticket))
    assert rt.session.treatments==1


@pytest.mark.parametrize("failure",["wrong_position","ungranted","version","missing","cross_patient","cross_context","v1_plan"])
def test_target_context_and_v1_bypass_rejected(tmp_path,failure):
    rt=runtime(tmp_path);ticket=rt.build_context();p=proxy_plan();code="TARGET_NOT_AUTHORIZED"
    if failure=="wrong_position":p["actions"][0]["compartment"]="LeftArm"
    elif failure=="ungranted":ticket=rt.build_context(authorized_locations=set())
    elif failure in ("version","missing"):
        rt.registry.invalidate(rt.registry.sources()[0].injury_id);code="STALE_SOURCE"
    elif failure=="cross_patient":p["patient_id"]="other";code="PATIENT_MISMATCH"
    elif failure=="cross_context":
        from dataclasses import replace
        ticket=replace(ticket,context_ref="another-patient-context");code="CONTEXT_NOT_FOUND"
    else:p=V1Plan(patient_id="P",actions=[]);code="INVALID_TREATMENT_SCHEMA"
    assert_code(code,lambda:execute(rt,p,ticket=ticket))
    assert rt.session.treatments==0


def test_provider_mutation_cannot_grant_new_position(tmp_path):
    rt=runtime(tmp_path);ticket=rt.build_context();ticket.public.known_injuries[0].compartment="LeftArm"
    p=proxy_plan();p["actions"][0]["compartment"]="LeftArm"
    assert_code("TARGET_NOT_AUTHORIZED",lambda:execute(rt,p,ticket=ticket))


def test_multiple_sources_rejected_without_first_source_selection():
    registry=InjuryRegistry("P");data=injury();data["injuries"].append({"injury_type":"external_hemorrhage","compartment":"LeftArm","severity":0.4})
    registry.register(CasualtyInput.model_validate(data))
    assert_code("UNVALIDATED_MULTISOURCE",lambda:registry.resolve("external_hemorrhage","RightLeg","P",registry.signature()))


def test_no_registry_source_or_wrong_type():
    registry=InjuryRegistry("P")
    assert_code("TARGET_NOT_FOUND",lambda:registry.resolve("external_hemorrhage","RightLeg","P",registry.signature()))
    registry.register(CasualtyInput.model_validate(injury()))
    assert_code("TARGET_NOT_AUTHORIZED",lambda:registry.resolve("abdominal_internal_hemorrhage","RightLeg","P",registry.signature()))


@pytest.mark.parametrize("credential",[None,"missing_stock","missing_medic","missing_procedure","wrong_patient","wrong_run","missing_capability"])
def test_resources_default_to_rejection(tmp_path,credential):
    resources=None if credential is None else explicit_test_resources("r","P")
    if credential=="missing_stock":resources.stock["blood_500ml_bag"]=0
    if credential=="missing_medic":resources.holds["medic"]=0
    if credential=="missing_procedure":resources.permissions=frozenset()
    if credential=="wrong_patient":resources.patient_id="another"
    if credential=="wrong_run":resources.run_id="another"
    if credential=="missing_capability":resources.capabilities=frozenset()
    rt=runtime(tmp_path,resources=resources)
    p={"patient_id":"P","actions":[{"action_type":"transfusion"}]} if credential=="missing_stock" else proxy_plan()
    with pytest.raises(V2Error):execute(rt,p)
    assert rt.session.treatments==0


def test_default_production_mode_disabled_and_no_v1_apply_entry(tmp_path):
    rt=CaseRuntime("P",tmp_path,run_id="r",session=SessionFaultFixture())
    assert_code("PRODUCTION_NOT_ENABLED",lambda:rt.prepare(injury()))
    from core301.pulse.v2.session import ResearchPulseSession
    assert not hasattr(ResearchPulseSession,"apply_treatment_actions")


@pytest.mark.parametrize("kind",["hemothorax","bronchoconstriction","acute_lung_impairment_ards"])
def test_reserved_injuries_never_initialize(tmp_path,kind):
    session=SessionFaultFixture();rt=CaseRuntime("P",tmp_path,run_id="r",mode="research",session=session)
    data=injury(kind)
    if kind=="hemothorax":data["injuries"][0]["side"]="Left"
    assert_code("INJURY_NOT_OPEN",lambda:rt.prepare(data))
    assert session.time==0 and not session.action_results


@pytest.mark.parametrize("kind",["chest_tube","inhaled_albuterol","control_hemothorax_bleeding","supplemental_oxygen"])
def test_reserved_action_or_mismatched_oxygen_cannot_bypass(tmp_path,kind):
    rt=runtime(tmp_path);action={"action_type":kind}
    if kind in ("chest_tube","control_hemothorax_bleeding"):action["side"]="Left"
    assert_code("ACTION_NOT_OPEN",lambda:execute(rt,{"patient_id":"P","actions":[action]}))
    assert rt.session.treatments==0


def test_native_rejection_halts_dependencies(tmp_path):
    session=SessionFaultFixture();session.fail_at=1
    rt=runtime(tmp_path,session=session,case=injury("respiratory_muscle_impairment"))
    p={"patient_id":"P","actions":[{"action_type":"intubation"},{"action_type":"mechanical_ventilation"}]}
    assert_code("NATIVE_REJECTED",lambda:execute(rt,p))
    record=rt.query("request")
    assert session.treatments==1 and record["actions"][0]["accepted"] is False
    assert record["actions"][1]["submitted_time_s"] is None and record["actions"][1]["lifecycle"]=="NOT_ATTEMPTED"


def test_unknown_submission_is_durable_and_never_replayed(tmp_path):
    session=SessionFaultFixture();session.unknown_at=1
    rt=runtime(tmp_path,session=session);ticket=rt.build_context()
    assert_code("SUBMISSION_UNKNOWN",lambda:execute(rt,ticket=ticket))
    record=execute(rt,ticket=ticket)
    assert record["actions"][0]["accepted"] is None and record["actions"][0]["state"]=="UNKNOWN"
    assert session.treatments==1
    reopened=CaseRuntime("P",tmp_path,run_id="r",mode="research",session=SessionFaultFixture())
    recovered=reopened.query("request")
    assert recovered["recovery_required"] and recovered["actions"][0]["lifecycle"]=="UNKNOWN"
    assert recovered["actions"][0]["accepted"] is None
    assert_code("RESTART_REQUIRES_RECOVERY",lambda:reopened.prepare(injury()))
    assert_code("RESTART_REQUIRES_RECOVERY",lambda:execute(reopened,request="different",ticket=ticket))


def test_partial_failure_keeps_source_acceptance_without_fallback(tmp_path):
    session=SessionFaultFixture();rt=runtime(tmp_path,session=session)
    session.after_submit=lambda n:rt.resources.stock.update({"blood_500ml_bag":-1}) if n==1 else None
    p=proxy_plan();p["actions"].append({"action_type":"transfusion"})
    assert_code("RESOURCE_UNAVAILABLE",lambda:execute(rt,p))
    record=rt.query("request")
    assert record["status"]=="FAILED_PARTIAL" and record["actions"][0]["accepted"] is True
    assert record["actions"][1]["submitted_time_s"] is None and session.treatments==1
    rt.advance(1)
    assert rt.query("request")["actions"][0]["lifecycle"]=="COMPLETED"
    assert rt.query("request")["status"]=="FAILED_PARTIAL"


def test_preflight_shortage_prevents_entire_plan(tmp_path):
    rt=runtime(tmp_path);rt.resources.stock["blood_500ml_bag"]=0
    p=proxy_plan();p["actions"].append({"action_type":"transfusion"})
    assert_code("RESOURCE_UNAVAILABLE",lambda:execute(rt,p))
    assert rt.session.treatments==0 and rt.query("request")["status"]=="REJECTED_BEFORE_EXECUTION"
    assert not any(e["state"]=="VALIDATED" for e in rt.journal.data["events"])


def test_bag_retry_and_device_retry_cannot_acquire_again(tmp_path):
    rt=runtime(tmp_path);p={"patient_id":"P","actions":[{"action_type":"transfusion"}]}
    execute(rt,p)
    assert rt.resources.stock["blood_500ml_bag"]==0
    assert_code("ACTION_REPLAY_BLOCKED",lambda:execute(rt,p,request="new-bag-id"))
    assert rt.session.treatments==1


def test_observation_is_not_rewritten_by_executor(tmp_path):
    rt=runtime(tmp_path);before=rt.observe().model_dump();execute(rt)
    assert rt.observe().model_dump()==before


def test_advance_failure_does_not_become_death_or_completed(tmp_path):
    rt=runtime(tmp_path);execute(rt)
    def fail(_):raise RuntimeError("injected advance failure")
    rt.session.advance_time=fail
    assert_code("ADVANCE_FAILED",lambda:rt.advance(1))
    item=rt.query("request")["actions"][0]
    assert item["lifecycle"]=="UNKNOWN" and item["error"]["code"]=="ADVANCE_FAILED"


def test_journal_write_precedes_native_submission_and_contains_required_fields(tmp_path):
    session=SessionFaultFixture();rt=runtime(tmp_path,session=session)
    def audit(_):
        d=json.loads((tmp_path/"execution_journal.json").read_text())
        assert d["plans"]["request"]["actions"][0]["state"]=="SUBMITTED"
    session.after_submit=audit
    execute(rt)
    item=rt.query("request")["actions"][0]
    for key in ["action_id","action_type","target","native_payload","protocol_id","submitted_time_s","accepted","lifecycle","validation","resource"]:
        assert key in item


def test_unregistered_native_source_cannot_be_selected_or_silently_ignored(tmp_path):
    rt=runtime(tmp_path)
    rt.session.state_actions["Hemorrhage"].append({"Compartment":"LeftArm","Severity":{"Scalar0To1":{"Value":0.4}}})
    assert_code("UNREGISTERED_NATIVE_SOURCE",lambda:execute(rt))
    assert rt.session.treatments==0


def test_initialization_failure_is_recorded_and_not_retried(tmp_path):
    session=SessionFaultFixture()
    def fail(*args):raise RuntimeError("injected Condition initialization failure")
    session.initialize=fail
    rt=CaseRuntime("P",tmp_path,run_id="r",mode="research",session=session)
    assert_code("INITIALIZATION_FAILED",lambda:rt.prepare(injury("dehydration")))
    report=json.loads((tmp_path/"initialization_result.json").read_text())
    assert report["accepted"] is False and session.action_results==[]


def test_unknown_close_preserves_uncertain_submission_fact(tmp_path):
    session=SessionFaultFixture();session.unknown_at=1
    rt=runtime(tmp_path,session=session)
    assert_code("SUBMISSION_UNKNOWN",lambda:execute(rt))
    rt.close()
    assert rt.query("request")["actions"][0]["lifecycle"]=="UNKNOWN"


def test_process_crash_leaves_write_ahead_record_and_recovery_blocks_resubmission(tmp_path):
    session=SessionFaultFixture();rt=runtime(tmp_path,session=session)
    def crash(*args):raise SystemExit("simulated process loss after write-ahead submit record")
    session._submit=crash;ticket=rt.build_context()
    with pytest.raises(SystemExit):execute(rt,ticket=ticket)
    durable=json.loads((tmp_path/"execution_journal.json").read_text())
    assert durable["plans"]["request"]["actions"][0]["state"]=="SUBMITTED"
    reopened=CaseRuntime("P",tmp_path,run_id="r",mode="research",session=SessionFaultFixture())
    recovered=reopened.query("request")
    assert recovered["recovery_required"] and recovered["actions"][0]["state"]=="UNKNOWN"
    assert reopened.execute_plan(proxy_plan(),request_id="request",context_ref=ticket.context_ref)==recovered
    assert reopened.session.treatments==0


def test_standalone_entry_refuses_implicit_resources_without_creating_patient(tmp_path):
    from core301.runtime.v2.demo import main
    output=tmp_path/"must-not-exist"
    with pytest.raises(SystemExit) as refused:
        main(["--injury","external_hemorrhage","--output",str(output)])
    assert refused.value.code==2 and not output.exists()


def test_source_revoked_between_actions_preserves_prefix_and_blocks_support(tmp_path):
    session=SessionFaultFixture();rt=runtime(tmp_path,session=session)
    source_id=rt.registry.sources()[0].injury_id
    session.after_submit=lambda n:rt.registry.invalidate(source_id) if n==1 else None
    p=proxy_plan();p["actions"].append({"action_type":"transfusion"})
    assert_code("STALE_SOURCE",lambda:execute(rt,p))
    assert session.treatments==1 and rt.query("request")["actions"][0]["accepted"] is True
    assert rt.query("request")["actions"][1]["submitted_time_s"] is None
    assert rt.resources.stock["blood_500ml_bag"]==1
    rt.advance(1)
    assert rt.query("request")["actions"][0]["lifecycle"]=="UNKNOWN"


def test_missing_authorized_safety_observations_blocks_oxygen(tmp_path):
    session=SessionFaultFixture()
    rt=CaseRuntime("P",tmp_path,run_id="r",mode="research",resources=explicit_test_resources("r","P"),session=session)
    rt.prepare(injury("impaired_alveolar_exchange"))
    p={"patient_id":"P","actions":[{"action_type":"supplemental_oxygen"}]}
    assert_code("MONITORING_UNAVAILABLE",lambda:execute(rt,p))
    assert session.treatments==0


def test_unverified_long_response_window_is_refused_without_advancing(tmp_path):
    rt=runtime(tmp_path)
    assert_code("UNVALIDATED_WINDOW",lambda:rt.advance(301))
    assert rt.session.time==180
