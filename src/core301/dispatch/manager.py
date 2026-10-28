"""Single-run, single-patient dispatch acceptance with backend-owned resource accounting.

Synchronous transactions contain no await; async callers revalidate here after waiting.
No database, inventory, autonomous replan, or Pulse execution is introduced.
"""
from uuid import uuid4
from .models import (CallContext, DispatchInput, DispatchProposal, DispatchTask, TaskEvent, ENDED)
from .validation import DispatchError, validate_proposal
from .events import validate_task_event


def changed(model, **updates):
    return type(model).model_validate({**model.model_dump(), **updates})


def detached(model):
    return type(model).model_validate(model.model_dump())


class ResourceManager:
    def __init__(self, initial_input, clock, *, known_patient_ids=(), tasks=(), onsite_capability=None, event_policy=None,
                 input_model=DispatchInput, proposal_validator=validate_proposal):
        self.input_model, self.proposal_validator = input_model, proposal_validator
        self._input = self.input_model.model_validate(initial_input)
        self._input = detached(self._input)
        self.clock, self.onsite_capability, self.event_policy = clock, onsite_capability, event_policy
        self.run_id = self._input.run_id
        self._active = True
        self._episode_ended = False
        self._known_patients = set(known_patient_ids) | {self._input.patient_id}
        self._facilities = {r.facility_id: detached(r) for r in self._input.facilities}
        self._ambulances = {r.ambulance_id: detached(r) for r in self._input.ambulances}
        self._teams = {r.team_id: detached(r) for r in self._input.medical_teams}
        values = [DispatchTask.model_validate(t) for t in tasks]
        self._tasks = {t.task_id: detached(t) for t in values}
        if len(values) != len(self._tasks):
            raise ValueError("duplicate task_id")
        self._accepted_calls, self._events, self._last_event = {}, {}, {}
        self._check_integrity(self._facilities, self._ambulances, self._teams, self._tasks)
        if self._input.current_facility_id is not None:
            f = self._facilities.get(self._input.current_facility_id)
            if f is None or self._input.patient_id not in f.admitted_patient_ids:
                raise ValueError("initial current facility requires an explicit admission")
        if self._input.patient_observation.simulation_time_s > clock.now_s:
            raise ValueError("observation is ahead of the global simulation clock")

    def ensure_active(self):
        if not self._active or self._episode_ended:
            raise DispatchError("DISPATCH_FAILED", "run or patient episode is no longer active")

    def stop_run(self):
        # Prevent late calls from applying changes; abnormal patient disposition is external.
        self._active = False

    def snapshot(self):
        return changed(self._input, facilities=[f.model_dump() for f in self._facilities.values()],
                       ambulances=[a.model_dump() for a in self._ambulances.values()],
                       medical_teams=[t.model_dump() for t in self._teams.values()])

    def task(self, task_id):
        if task_id not in self._tasks:
            raise DispatchError("DISPATCH_FAILED", "unknown task")
        return detached(self._tasks[task_id])

    def _owned_task(self, task_id):
        task = self.task(task_id)
        if task.patient_id != self._input.patient_id:
            raise DispatchError("DISPATCH_FAILED", "this manager does not own that patient runtime")
        return task

    def _check_integrity(self, facilities, ambulances, teams, tasks):
        for f in facilities.values():
            type(f).model_validate(f.model_dump())
            if f.run_id != self.run_id or not set(f.reserved_patient_ids + f.admitted_patient_ids) <= self._known_patients:
                raise ValueError("facility contains unknown/cross-run patient references")
        active_patients = set()
        for task in tasks.values():
            if task.run_id != self.run_id or task.patient_id not in self._known_patients:
                raise ValueError("unknown/cross-run task patient")
            if task.mode == "evacuation" and (task.ambulance_id not in ambulances or task.target_facility_id not in facilities):
                raise ValueError("task references unknown evacuation resources")
            if task.mode == "team_response" and task.team_id not in teams:
                raise ValueError("task references unknown team")
            if task.state not in ENDED:
                if task.patient_id in active_patients:
                    raise ValueError("patient has multiple active tasks")
                active_patients.add(task.patient_id)
                r = ambulances[task.ambulance_id] if task.mode == "evacuation" else teams[task.team_id] if task.mode == "team_response" else None
                if r is not None and r.active_task_id != task.task_id:
                    raise ValueError("active task/resource association is inconsistent")
        for resources, key, mode in ((ambulances, "ambulance_id", "evacuation"), (teams, "team_id", "team_response")):
            for resource_id, r in resources.items():
                if r.run_id != self.run_id:
                    raise ValueError("cross-run resource")
                if r.active_task_id is not None:
                    task = tasks.get(r.active_task_id)
                    if task is None or task.state in ENDED or task.mode != mode or getattr(task, key) != resource_id:
                        raise ValueError("active_task_id must reference a matching unfinished task")

    def _commit(self, task, *, facility=None, ambulance=None, team=None, facilities=None):
        fs, ars, ts, tasks = dict(self._facilities), dict(self._ambulances), dict(self._teams), dict(self._tasks)
        if facilities is not None:
            fs = facilities
        if facility is not None:
            fs[facility.facility_id] = facility
        if ambulance is not None:
            ars[ambulance.ambulance_id] = ambulance
        if team is not None:
            ts[team.team_id] = team
        if task is not None:
            tasks[task.task_id] = task
        self._check_integrity(fs, ars, ts, tasks)
        self._facilities, self._ambulances, self._teams, self._tasks = fs, ars, ts, tasks

    def accept(self, context, payload, proposal):
        self.ensure_active()
        context = CallContext.model_validate(context)
        payload = self.input_model.model_validate(payload)
        proposal = DispatchProposal.model_validate(proposal.model_dump() if hasattr(proposal, "model_dump") else proposal)
        if (context.run_id, context.patient_id) != (self.run_id, self._input.patient_id) or (payload.run_id, payload.patient_id) != (context.run_id, context.patient_id):
            raise DispatchError("DISPATCH_FAILED", "dispatch context identity mismatch")
        request = {"payload": payload.model_dump(), "proposal": proposal.model_dump()}
        if context.call_id in self._accepted_calls:
            old, task_id = self._accepted_calls[context.call_id]
            if old != request:
                raise DispatchError("DISPATCH_FAILED", "accepted call_id reused for a different request")
            return self.task(task_id)
        if any(t.patient_id == payload.patient_id and t.state not in ENDED for t in self._tasks.values()):
            raise DispatchError("RESOURCE_UNAVAILABLE", "patient already has an unfinished dispatch task")
        if payload.treatment_plan != self._input.treatment_plan:
            raise DispatchError("DISPATCH_FAILED", "dispatch cannot replace the upstream treatment plan")
        if (payload.position, payload.current_facility_id) != (self._input.position, self._input.current_facility_id):
            raise DispatchError("RESOURCE_UNAVAILABLE", "patient location changed while dispatch was pending")
        if payload.patient_observation.simulation_time_s > self.clock.now_s:
            raise DispatchError("DISPATCH_FAILED", "observation is ahead of the global simulation clock")
        # First enforce offered IDs, then check fresh authoritative availability/capability.
        self.proposal_validator(payload, proposal, onsite_capability=self.onsite_capability)
        current = changed(payload,
                          facilities=[self._facilities[f.facility_id].model_dump() for f in payload.facilities if f.facility_id in self._facilities],
                          ambulances=[self._ambulances[a.ambulance_id].model_dump() for a in payload.ambulances if a.ambulance_id in self._ambulances],
                          medical_teams=[self._teams[t.team_id].model_dump() for t in payload.medical_teams if t.team_id in self._teams])
        self.proposal_validator(current, proposal, onsite_capability=self.onsite_capability)
        if proposal.mode == "evacuation" and payload.current_facility_id is not None:
            raise DispatchError("RESOURCE_UNAVAILABLE", "inter-facility transfer/release policy is not confirmed")
        task = DispatchTask(**proposal.model_dump(), task_id=uuid4().hex, run_id=self.run_id,
                            state="assigned", accepted_at_s=self.clock.now_s,
                            treatment_ready_at_s=self.clock.now_s if proposal.mode == "onsite" else None,
                            ended_at_s=None, detail=None)
        facility = ambulance = team = None
        if task.mode == "evacuation":
            f = self._facilities[task.target_facility_id]
            facility = changed(f, reserved_patient_ids=[*f.reserved_patient_ids, task.patient_id])
            ambulance = changed(self._ambulances[task.ambulance_id], active_task_id=task.task_id)
        elif task.mode == "team_response":
            team = changed(self._teams[task.team_id], active_task_id=task.task_id)
        self._commit(task, facility=facility, ambulance=ambulance, team=team)
        self._accepted_calls[context.call_id] = (request, task.task_id)
        return detached(task)

    def apply_event(self, event):
        self.ensure_active()
        event = TaskEvent.model_validate(event)
        if event.run_id != self.run_id:
            raise DispatchError("DISPATCH_FAILED", "cross-run event")
        if event.event_id in self._events:
            previous, result = self._events[event.event_id]
            if previous != event:
                raise DispatchError("DISPATCH_FAILED", "event_id reused with different facts")
            return detached(result)
        task = self.task(event.task_id)
        if task.patient_id != self._input.patient_id:
            raise DispatchError("DISPATCH_FAILED", "this manager does not own that patient runtime")
        facility = self._facilities.get(task.target_facility_id)
        transition = validate_task_event(task, event, now_s=self.clock.now_s,
                                         last_event_at_s=self._last_event.get(task.task_id, task.accepted_at_s),
                                         policy=self.event_policy, patient_position=detached(self._input.position),
                                         facility_position=detached(facility.position) if facility else None)
        task = changed(task, state=transition.state,
                       treatment_ready_at_s=event.occurred_at_s if transition.treatment_ready else task.treatment_ready_at_s)
        ambulance = changed(self._ambulances[task.ambulance_id], position=event.position.model_dump()) if task.ambulance_id else None
        team = changed(self._teams[task.team_id], position=event.position.model_dump()) if task.team_id else None
        next_input = self._input
        if event.kind in ("transport_started", "arrived_at_facility"):
            next_input = changed(self._input, position=event.position.model_dump())
        self._commit(task, ambulance=ambulance, team=team)
        self._input = next_input
        self._last_event[task.task_id] = event.occurred_at_s
        self._events[event.event_id] = (detached(event), detached(task))
        return detached(task)

    def confirm_facility_admission(self, task_id):
        self.ensure_active()
        task = self._owned_task(task_id)
        if task.mode != "evacuation" or task.state != "at_facility":
            raise DispatchError("DISPATCH_FAILED", "facility admission requires confirmed evacuation arrival")
        f = self._facilities[task.target_facility_id]
        if task.patient_id not in f.reserved_patient_ids:
            raise DispatchError("RESOURCE_UNAVAILABLE", "task has no facility reservation")
        facility = changed(f, reserved_patient_ids=[p for p in f.reserved_patient_ids if p != task.patient_id],
                           admitted_patient_ids=[*f.admitted_patient_ids, task.patient_id])
        task = changed(task, state="completed", ended_at_s=self.clock.now_s, treatment_ready_at_s=self.clock.now_s)
        ambulance = changed(self._ambulances[task.ambulance_id], active_task_id=None)
        next_input = changed(self._input, current_facility_id=f.facility_id, position=f.position.model_dump())
        self._commit(task, facility=facility, ambulance=ambulance)
        self._input = next_input
        return detached(task)

    def confirm_onsite(self, task_id):
        self.ensure_active()
        task = self._owned_task(task_id)
        if task.mode != "onsite" or task.state != "assigned":
            raise DispatchError("DISPATCH_FAILED", "onsite confirmation requires an assigned onsite task")
        self.proposal_validator(self.snapshot(), DispatchProposal.model_validate({k: task.model_dump()[k] for k in DispatchProposal.model_fields}),
                          onsite_capability=self.onsite_capability)
        task = changed(task, state="completed", ended_at_s=self.clock.now_s)
        self._commit(task)
        return detached(task)

    def terminate(self, task_id, *, state, detail):
        self.ensure_active()
        task = self._owned_task(task_id)
        if state not in ("failed", "cancelled") or task.state in ENDED:
            raise DispatchError("DISPATCH_FAILED", "only unfinished tasks can fail or be cancelled")
        task = changed(task, state=state, detail=detail, ended_at_s=self.clock.now_s)
        facility = ambulance = team = None
        if task.mode == "evacuation":
            f = self._facilities[task.target_facility_id]
            facility = changed(f, reserved_patient_ids=[p for p in f.reserved_patient_ids if p != task.patient_id])
            ambulance = changed(self._ambulances[task.ambulance_id], active_task_id=None)
        elif task.mode == "team_response":
            team = changed(self._teams[task.team_id], active_task_id=None)
        self._commit(task, facility=facility, ambulance=ambulance, team=team)
        return detached(task)

    def end_episode(self, *, unfinished_task_outcome=None, detail=None):
        """Backend-confirmed episode end; caller explicitly chooses unfinished-task disposition."""
        self.ensure_active()
        active = next((t for t in self._tasks.values() if t.patient_id == self._input.patient_id and t.state not in ENDED), None)
        if active is not None:
            if unfinished_task_outcome == "completed" and active.mode == "team_response" and active.state == "at_patient":
                task = changed(active, state="completed", ended_at_s=self.clock.now_s)
                self._commit(task, team=changed(self._teams[task.team_id], active_task_id=None))
            elif unfinished_task_outcome in ("failed", "cancelled"):
                self.terminate(active.task_id, state=unfinished_task_outcome, detail=detail)
            else:
                raise DispatchError("DISPATCH_FAILED", "backend must explicitly resolve the unfinished task before ending episode")
        patient_id = self._input.patient_id
        facilities = {key: changed(f, reserved_patient_ids=[p for p in f.reserved_patient_ids if p != patient_id],
                                    admitted_patient_ids=[p for p in f.admitted_patient_ids if p != patient_id])
                      for key, f in self._facilities.items()}
        self._commit(None, facilities=facilities)
        self._episode_ended = True
