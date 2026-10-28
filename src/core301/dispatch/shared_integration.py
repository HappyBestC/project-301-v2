"""M2-B: stage existing dispatch logic, reserve M2-A, then publish both under one lock.

No Agent/ETA await holds a lock. Legacy state is canonical per run, never per
patient inventory. Existing ResourceManager instances are detached transition
engines, and are not exposed as independent writers.
"""
from copy import deepcopy
from dataclasses import dataclass, field, asdict
import json
from typing import Literal

from .complete_contracts import (CompleteDispatchInput, CompletePlan, decode_dispatch_input,
                                 validate_complete_proposal, ACTION_TYPES as COMPLETE_ACTION_TYPES)
from .manager import ResourceManager
from .models import DispatchInput, DispatchTask, CallContext, CallFailure
from .clock import SimulationClock
from .eta import EtaAdapter
from .service import decide_dispatch
from .validation import DispatchError
from core301.contracts.treatment import ACTION_TYPES
from .shared_resources import SharedResourceManager, Request, Plan, Result, Conflict
from .shared_resources.models import Model
from .shared_resources.catalog import Catalog


class DispatchOutcome(Model):
    schema_version: Literal['301.dispatch.shared.1'] = '301.dispatch.shared.1'
    allocated: bool
    resource_result: Result
    legacy_state_version: int
    task: DispatchTask | None = None
    needs_replanning: bool = False


@dataclass
class _Run:
    managers: dict
    facilities: dict
    ambulances: dict
    teams: dict
    tasks: dict
    clock: SimulationClock
    patient_locations: dict
    facility_locations: dict
    legacy_assets_disjoint: bool | None
    legacy_version: int = 0
    requests: dict = field(default_factory=dict)
    inflight: dict = field(default_factory=dict)
    task_plans: dict = field(default_factory=dict)
    lifecycle_requests: dict = field(default_factory=dict)
    call_ids: dict = field(default_factory=dict)


class SharedDispatchCoordinator:
    def __init__(self, resources: SharedResourceManager):
        self.resources = resources
        self._runs = {}
        self._catalog = Catalog()

    def register_run(self, run_id, inputs, *, at_s, patient_locations,
                     facility_locations=None, legacy_assets_disjoint=None, event_policy=None):
        """Explicit backend topology. No quantities are copied from legacy objects.

        legacy_assets_disjoint must be explicitly True for team/evacuation: the
        old vehicle/team/capacity assets must not also be M2-A physical tokens.
        A missing/false declaration fails closed instead of inventing ownership.
        """
        sources = [decode_dispatch_input(x) for x in inputs]
        if not sources or any(s.run_id != run_id for s in sources):
            raise ValueError('nonempty same-run dispatch inputs required')
        patients = {s.patient_id for s in sources}
        if len(patients) != len(sources) or set(patient_locations) != patients:
            raise ValueError('unique patients and exact patient location bindings required')
        first = sources[0]
        for s in sources[1:]:
            if ([x.model_dump() for x in s.facilities],s.ambulances,[x.model_dump() for x in s.medical_teams]) != ([x.model_dump() for x in first.facilities],first.ambulances,[x.model_dump() for x in first.medical_teams]):
                raise ValueError('all patients must reference the same initial legacy asset state')
        if legacy_assets_disjoint is not None and type(legacy_assets_disjoint) is not bool:
            raise ValueError('explicit bool or unknown ownership declaration required')
        if any(r.active_task_id for r in first.ambulances+first.medical_teams):
            raise ValueError('importing pre-existing transport tasks is not supported')
        with self.resources.serialized(run_id):
            if run_id in self._runs:
                raise ValueError('dispatch run already registered')
            shared = self.resources.get_snapshot(run_id)
            if at_s < shared['at_s']:
                raise ValueError('dispatch registration cannot precede shared simulation time')
            bindings = [*patient_locations.values(), *(facility_locations or {}).values()]
            if any(x not in shared['locations'] for x in bindings):
                raise ValueError('location binding must reference an existing M2-A location')
            if set(facility_locations or {}) - {f.facility_id for f in first.facilities}:
                raise ValueError('unknown facility binding')
            legacy_ids = {f.facility_id for f in first.facilities} | {a.ambulance_id for a in first.ambulances} | {t.team_id for t in first.medical_teams}
            if legacy_ids.intersection(shared['resources']):
                raise ValueError('same canonical asset cannot be owned by both ledgers')
            clock = SimulationClock(at_s)
            managers = {s.patient_id: ResourceManager(s,clock,known_patient_ids=patients,event_policy=event_policy,
                        **(dict(input_model=CompleteDispatchInput,proposal_validator=validate_complete_proposal)
                           if isinstance(s,CompleteDispatchInput) else {}))
                        for s in sources}
            self._runs[run_id] = _Run(managers,
                {f.facility_id: f.model_copy(deep=True) for f in first.facilities},
                {a.ambulance_id: a.model_copy(deep=True) for a in first.ambulances},
                {t.team_id: t.model_copy(deep=True) for t in first.medical_teams}, {}, clock,
                deepcopy(patient_locations), deepcopy(facility_locations or {}), legacy_assets_disjoint)

    def _run(self, run_id):
        if run_id not in self._runs:
            raise ValueError('dispatch run not registered; no fallback to legacy-only inventory')
        return self._runs[run_id]

    def _stage(self, run_id, patient_id):
        run = self._run(run_id)
        stage = deepcopy(run.managers[patient_id])
        stage.clock = deepcopy(run.clock)
        stage._facilities = deepcopy(run.facilities)
        stage._ambulances = deepcopy(run.ambulances)
        stage._teams = deepcopy(run.teams)
        stage._tasks = deepcopy(run.tasks)
        stage._known_patients = set(run.managers)
        # The callback is backend-owned and reads only the bound current location.
        loc_id = (run.facility_locations.get(stage._input.current_facility_id)
                  if stage._input.current_facility_id else run.patient_locations[patient_id])
        loc = self.resources.get_snapshot(run_id)['locations'].get(loc_id)
        caps = None if not loc or loc['capabilities'] is None else frozenset(loc['capabilities']).intersection(COMPLETE_ACTION_TYPES if isinstance(stage._input,CompleteDispatchInput) else ACTION_TYPES)
        stage.onsite_capability = lambda _: caps
        return stage

    @staticmethod
    def _publish(run, patient_id, stage):
        # Only assignments follow the successful reserve. No I/O, validation,
        # callbacks or awaits occur here. Lock prevents intermediate observation.
        run.managers[patient_id] = stage
        run.facilities, run.ambulances, run.teams, run.tasks = stage._facilities, stage._ambulances, stage._teams, stage._tasks
        run.clock = stage.clock
        run.legacy_version += 1

    def dispatch_input(self, run_id, patient_id):
        with self.resources.serialized(run_id):
            return self._stage(run_id,patient_id).snapshot()

    def get_history(self, run_id):
        """Detached scheduling/lifecycle receipts; medical facts remain in M2-A events."""
        with self.resources.serialized(run_id):
            run = self._run(run_id)
            return [dict(operation=operation, request=json.loads(fp)['request'],
                         result=result.model_dump(mode='json'))
                    for operation, records in (('schedule', run.requests), ('lifecycle', run.lifecycle_requests))
                    for fp, result in records.values()]

    def _projection(self, run_id, plan):
        s = self.resources.get_snapshot(run_id)
        run = self._run(run_id)
        # Explicit public data only: no manager, private execution state, source
        # registry or raw event stream enters the provider/LLM payload.
        fields = ('resource_id','resource_type_id','unit','location_id','use_mode','total_qty',
                  'available_qty','reserved_qty','in_use_qty','unavailable_qty','operational_state')
        return dict(schema_version='301.dispatch.resource_view.1', run_id=run_id,
                    state_version=s['state_version'], legacy_state_version=run.legacy_version,
                    scope_kind=plan.scope_kind, resources=[{k:r[k] for k in fields} for r in s['resources'].values()],
                    locations=deepcopy(s['locations']),
                    research_requirements=[asdict(self._catalog.requirements[a.action_type]) for a in plan.actions
                                           if a.action_type in self._catalog.requirements], constraints={
                        'treatment_plan_is_read_only':True, 'backend_reservation_required':True,
                        'clinical_requirements_unconfirmed':True,
                        'patient_location_id':run.patient_locations[plan.patient_id],
                        'requested_treatment_location_id':plan.location_id,
                        'facility_locations':deepcopy(run.facility_locations),
                        'legacy_assets_disjoint':run.legacy_assets_disjoint,
                        'unsupported_dispatch_actions':sorted(set(a.action_type for a in plan.actions)-set(
                            COMPLETE_ACTION_TYPES if isinstance(run.managers[plan.patient_id]._input,CompleteDispatchInput) else ACTION_TYPES))})

    def _failure(self, req, code, detail, *, outcome=None):
        run = self._run(req.run_id)
        version = self.resources.get_snapshot(req.run_id)['state_version']
        unknown = code in ('CONSTRAINT_UNKNOWN','EXECUTION_UNCERTAIN','REQUEST_IN_PROGRESS')
        result = Result(run_id=req.run_id,patient_id=req.patient_id,plan_id=req.plan_id,
            request_id=req.request_id,state_version=version,
            outcome=outcome or ('INDETERMINATE' if unknown else 'UNSATISFIED'),
            conflicts=(Conflict(code=code,run_id=req.run_id,patient_id=req.patient_id,plan_id=req.plan_id,
                action_instance_id=req.action_instance_id,state_version=version,detail=detail),))
        return DispatchOutcome(allocated=False,resource_result=result,legacy_state_version=run.legacy_version,
                               needs_replanning=not unknown)

    @staticmethod
    def _same_plan(source, plan):
        if isinstance(source,CompleteDispatchInput):
            return source.treatment_plan.to_resource_plan()==plan
        actions = []
        for a in plan.actions:
            data = {'action_type':a.action_type}
            if a.side is not None:
                data['side']=a.side
            if a.compartment is not None:
                data['compartment']=a.compartment
            actions.append(data)
        return (source.patient_id == plan.patient_id and
                source.treatment_plan.model_dump() == {'patient_id':plan.patient_id,'actions':actions})

    async def schedule_complete(self, request, plan, provider, eta_provider):
        from pydantic import ValidationError
        req=Request.model_validate(request)
        data=plan.model_dump() if hasattr(plan,'model_dump') else plan
        with self.resources.serialized(req.run_id):
            if not isinstance(data,dict) or data.get('schema_version')!='301.treatment.complete.1':
                return self._failure(req,'CONTRACT_VERSION_UNSUPPORTED','Expected complete plan version 1')
            try:
                complete=CompletePlan.model_validate(data)
            except ValidationError as exc:
                code=exc.errors()[0]['type']
                if code not in ('DEPENDENCY_UNMET','INCOMPATIBLE_RESOURCE','CONSTRAINT_UNKNOWN','CAPABILITY_UNAVAILABLE'):
                    code='PLAN_SEMANTICS_INVALID'
                return self._failure(req,code,'Complete plan rejected: '+str(exc))
            run=self._run(req.run_id)
            if req.patient_id not in run.managers or complete.run_id!=req.run_id:
                return self._failure(req,'IDENTITY_MISMATCH','Complete plan run/patient mismatch')
            source=run.managers[req.patient_id]._input
            if not isinstance(source,CompleteDispatchInput) or source.treatment_plan!=complete:
                return self._failure(req,'PLAN_MISMATCH','Complete upstream plan must remain unchanged')
        return await self.schedule(req,complete.to_resource_plan(),provider,eta_provider)

    async def schedule(self, request, plan, provider, eta_provider):
        req, plan = Request.model_validate(request), Plan.model_validate(plan)
        fp = json.dumps({'request':req.model_dump(mode='json'),'plan':plan.model_dump(mode='json')},sort_keys=True)
        with self.resources.serialized(req.run_id):
            run=self._run(req.run_id)
            if req.idempotency_key in run.lifecycle_requests:
                return self._failure(req,'IDEMPOTENCY_CONFLICT','Key already used for lifecycle operation')
            old=run.requests.get(req.idempotency_key) or run.inflight.get(req.idempotency_key)
            if old:
                if old[0]!=fp:
                    return self._failure(req,'IDEMPOTENCY_CONFLICT','Dispatch key reused with different input')
                if req.idempotency_key in run.requests:
                    return old[1].model_copy(deep=True)
                return self._failure(req,'REQUEST_IN_PROGRESS','Identical decision is already in flight; do not issue a new treatment')
            def reject(code, detail):
                answer = self._failure(req, code, detail)
                run.requests[req.idempotency_key] = (fp, answer.model_copy(deep=True))
                return answer
            if req.action_instance_id is not None or (req.patient_id,req.plan_id)!=(plan.patient_id,plan.plan_id):
                return reject('IDENTITY_MISMATCH','Whole-plan request identity mismatch')
            if req.patient_id not in run.managers:
                return reject('IDENTITY_MISMATCH','Patient not registered')
            source=self._stage(req.run_id,req.patient_id).snapshot()
            if not isinstance(source,CompleteDispatchInput) and any(a.action_type not in ACTION_TYPES for a in plan.actions):
                return reject('ACTION_CONTRACT_UNSUPPORTED','Frozen DispatchInput cannot represent the complete plan; no actions were dropped')
            if not self._same_plan(source,plan):
                return reject('PLAN_MISMATCH','Resource plan cannot replace the upstream TreatmentPlan')
            view=self._projection(req.run_id,plan)
            if req.expected_state_version!=view['state_version']:
                return reject('STALE_SNAPSHOT','Shared snapshot already changed')
            if req.request_id in run.call_ids:
                return reject('IDEMPOTENCY_CONFLICT','request_id already used with another idempotency key')
            run.call_ids[req.request_id]=req.idempotency_key
            legacy_version=run.legacy_version
            run.inflight[req.idempotency_key]=(fp,None)
        context=CallContext(run_id=req.run_id,patient_id=req.patient_id,call_id=req.request_id)
        def ensure_active():
            with self.resources.serialized(req.run_id):
                self._stage(req.run_id,req.patient_id).ensure_active()
        eta=EtaAdapter(lambda:self.dispatch_input(req.run_id,req.patient_id),eta_provider,ensure_active)
        try:
            response=await decide_dispatch(context,source,provider,eta.query_eta,
                                           ensure_active=ensure_active,shared_resources=view)
            with self.resources.serialized(req.run_id):
                run=self._run(req.run_id)
                if isinstance(response,CallFailure):
                    answer=self._failure(req,response.error.code,response.error.message)
                elif legacy_version!=run.legacy_version:
                    answer=self._failure(req,'STALE_SNAPSHOT','Legacy transport/facility state changed during the decision')
                else:
                    answer=self._confirm(req,plan,source,response.data,context)
                run.requests[req.idempotency_key]=(fp,answer.model_copy(deep=True))
                return answer
        finally:
            with self.resources.serialized(req.run_id):
                self._run(req.run_id).inflight.pop(req.idempotency_key,None)

    def _confirm(self, req, plan, source, proposal, context):
        run=self._run(req.run_id)
        if proposal.mode!='onsite' and run.legacy_assets_disjoint is not True:
            return self._failure(req,'CONSTRAINT_UNKNOWN','Transport/team assets may overlap medical tokens; ownership is not established')
        expected=(run.facility_locations.get(proposal.target_facility_id) if proposal.mode=='evacuation' else
                  run.facility_locations.get(source.current_facility_id) if source.current_facility_id else
                  run.patient_locations[req.patient_id])
        if expected is None:
            return self._failure(req,'CONSTRAINT_UNKNOWN','No authoritative treatment location binding')
        if plan.location_id!=expected:
            return self._failure(req,'LOCATION_MISMATCH','Proposed dispatch destination differs from the resource plan location')
        # M2-A checks unknown clinical/capability conditions before the old boolean
        # capability contract could collapse unknown into an ordinary rejection.
        check=self.resources.evaluate_requirements(req,plan)
        if check.outcome!='SATISFIED':
            return DispatchOutcome(allocated=False,resource_result=check,legacy_state_version=run.legacy_version,
                                   needs_replanning=check.outcome=='UNSATISFIED')
        stage=self._stage(req.run_id,req.patient_id)
        try:
            stage.clock.advance_to(req.at_s)
            task=stage.accept(context,source,proposal)
        except (ValueError,DispatchError) as exc:
            code=exc.code if isinstance(exc,DispatchError) else 'DISPATCH_FAILED'
            return self._failure(req,code,str(exc))
        # Legacy changes above are detached. If M2-A fails, discard the entire
        # stage: no legacy reservation ever became visible and nothing to undo.
        result=self.resources.reserve(req,plan)
        if result.outcome!='SATISFIED':
            return DispatchOutcome(allocated=False,resource_result=result,legacy_state_version=run.legacy_version,
                                   needs_replanning=result.outcome=='UNSATISFIED')
        self._publish(run,req.patient_id,stage)
        run.task_plans[task.task_id]=(req.patient_id,plan.plan_id)
        return DispatchOutcome(allocated=True,resource_result=result,legacy_state_version=run.legacy_version,
                               task=task,needs_replanning=False)

    def lifecycle(self, request, task_id, operation, *, event=None, detail=None):
        """Reuse old event/arrival/admission/termination semantics under the same lock.

        Cancellation/end is allowed only after all started medical usage has
        ended; UNKNOWN never silently releases team/vehicle/capacity holdings.
        Remaining unstarted medical reservations are cancelled atomically.
        """
        req=Request.model_validate(request)
        if req.action_instance_id is not None:
            raise ValueError('lifecycle request uses action_instance_id=null')
        payload=dict(request=req.model_dump(mode='json'),task_id=task_id,operation=operation,
                     event=event.model_dump(mode='json') if hasattr(event,'model_dump') else event,detail=detail)
        fp=json.dumps(payload,sort_keys=True)
        with self.resources.serialized(req.run_id):
            run=self._run(req.run_id)
            if req.idempotency_key in run.requests or req.idempotency_key in run.inflight:
                return self._failure(req,'IDEMPOTENCY_CONFLICT','Key already used for scheduling')
            old=run.lifecycle_requests.get(req.idempotency_key)
            if old:
                if old[0]!=fp:
                    return self._failure(req,'IDEMPOTENCY_CONFLICT','Lifecycle key reused')
                return old[1].model_copy(deep=True)
            answer=self._lifecycle(req,task_id,operation,event,detail)
            run.lifecycle_requests[req.idempotency_key]=(fp,answer.model_copy(deep=True))
            return answer

    def _lifecycle(self,req,task_id,operation,event,detail):
        run=self._run(req.run_id)
        if run.task_plans.get(task_id)!=(req.patient_id,req.plan_id):
            return self._failure(req,'IDENTITY_MISMATCH','Task and medical plan ownership mismatch')
        s=self.resources.get_snapshot(req.run_id)
        if req.expected_state_version!=s['state_version']:
            return self._failure(req,'STALE_SNAPSHOT','Read current resource state first')
        if req.at_s < s['at_s']:
            return self._failure(req,'DISPATCH_FAILED','Lifecycle simulation time precedes medical ledger')
        ending=operation in ('cancel','fail','end_episode')
        if ending:
            active=[a for a in s['allocations'].values() if a['plan_id']==req.plan_id and a['status'] in ('IN_USE','QUARANTINED')]
            states=s['plans'][req.plan_id]['actions'].values()
            if active or any(x['status'] in ('STARTED','QUARANTINED') for x in states):
                return self._failure(req,'EXECUTION_UNCERTAIN','Confirm medical usage has stopped before releasing legacy task assets')
        stage=self._stage(req.run_id,req.patient_id)
        try:
            stage.clock.advance_to(req.at_s)
            if operation=='event':
                from .models import TaskEvent
                ev=TaskEvent.model_validate(event)
                if ev.task_id!=task_id:
                    raise ValueError('event task mismatch')
                task=stage.apply_event(ev)
            elif operation=='admit':
                task=stage.confirm_facility_admission(task_id)
            elif operation=='confirm_onsite':
                task=stage.confirm_onsite(task_id)
            elif operation in ('cancel','fail'):
                task=stage.terminate(task_id,state='cancelled' if operation=='cancel' else 'failed',detail=detail)
            elif operation=='end_episode':
                stage.end_episode(unfinished_task_outcome='completed')
                task=stage.task(task_id)
            else:
                raise ValueError('unsupported lifecycle operation')
        except (ValueError,DispatchError) as exc:
            return self._failure(req,'DISPATCH_FAILED',str(exc))
        if ending:
            result=self.resources.release_unused(req,reason=detail or operation)
            if result.outcome!='SATISFIED':
                return DispatchOutcome(allocated=False,resource_result=result,legacy_state_version=run.legacy_version)
        else:
            result=Result(run_id=req.run_id,patient_id=req.patient_id,plan_id=req.plan_id,request_id=req.request_id,
                          state_version=s['state_version'],outcome='SATISFIED')
        self._publish(run,req.patient_id,stage)
        return DispatchOutcome(allocated=False,resource_result=result,legacy_state_version=run.legacy_version,task=task)

    def begin_usage(self, request, task_id):
        req=Request.model_validate(request)
        with self.resources.serialized(req.run_id):
            run=self._run(req.run_id)
            if run.task_plans.get(task_id)!=(req.patient_id,req.plan_id):
                return self._failure(req,'IDENTITY_MISMATCH','Task and plan mismatch').resource_result
            task=run.tasks[task_id]
            if task.state in ('cancelled','failed') or task.treatment_ready_at_s is None:
                return self._failure(req,'DEPENDENCY_UNMET','Existing dispatch lifecycle has not confirmed treatment readiness').resource_result
            if req.at_s < task.treatment_ready_at_s:
                return self._failure(req,'DEPENDENCY_UNMET','Medical use precedes treatment readiness').resource_result
            return self.resources.begin_usage(req)
