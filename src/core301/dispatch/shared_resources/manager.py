"""One backend-owned, thread-safe in-memory authority; no Pulse/Agent side effects."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4
import json

from .catalog import Catalog
from .models import (Request, Resource, Location, Plan, Execution, ReleaseEvidence,
                     ResourceChange, Conflict, Result)


@dataclass
class ResourceState:
    definition: Resource
    location_id: str | None
    received: int = 0
    consumed: int = 0
    lost: int = 0
    blocked: str | None = None


@dataclass
class Allocation:
    allocation_id: str
    patient_id: str
    plan_id: str
    resource_id: str
    quantity: int
    unit: str
    use_mode: str
    action_instance_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    status: str = 'RESERVED'
    consumed_qty: int = 0
    active_action_id: str | None = None
    start_at_s: float | None = None
    actual_end_at_s: float | None = None


@dataclass
class PlanState:
    definition: Plan
    actions: dict = field(default_factory=dict)
    cancelled: bool = False


@dataclass
class RunState:
    resources: dict
    locations: dict
    views: dict
    version: int = 0
    at_s: float = 0
    allocations: dict = field(default_factory=dict)
    plans: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)
    events: list = field(default_factory=list)


class SharedResourceManager:
    """Instantiate once per backend and inject it into every patient caller.

    All methods use the same RLock. Mutation uses a private copy and commits only
    after invariants pass. Neither snapshots nor input models alias internal data.
    There is deliberately no process-global singleton, persistence or wall clock.
    """
    def __init__(self):
        self._lock = RLock()
        self._runs = {}
        self._catalog = Catalog()

    def create_run(self, run_id, resources, locations, *, views=None):
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError('nonblank run_id required')
        resources = [Resource.model_validate(x).model_copy(deep=True) for x in resources]
        locations = [Location.model_validate(x).model_copy(deep=True) for x in locations]
        rs = {r.resource_id: ResourceState(r, r.location_id) for r in resources}
        ls = {l.location_id: l for l in locations}
        if len(rs) != len(resources) or len(ls) != len(locations):
            raise ValueError('duplicate canonical resource/location identity')
        for r in resources:
            if self._catalog.resources.get(r.resource_type_id) != (r.unit, r.use_mode):
                raise ValueError('research resource type/unit/use_mode does not match existing COSTS')
            if r.location_id is not None and r.location_id not in ls:
                raise ValueError('unknown resource location')
        aliases = deepcopy(views or {})
        for name, ids in aliases.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(ids, (tuple, list)):
                raise ValueError('views map a name to canonical resource IDs')
            if len(set(ids)) != len(ids) or not set(ids) <= rs.keys():
                raise ValueError('duplicate/unknown resource reference in view')
        with self._lock:
            if run_id in self._runs:
                raise ValueError('run already exists; cannot reset shared inventory')
            self._runs[run_id] = RunState(rs, ls, aliases)

    def _run(self, run_id):
        if run_id not in self._runs:
            raise ValueError('unknown run_id')
        return self._runs[run_id]

    @contextmanager
    def serialized(self, run_id):
        """Trusted synchronous integration boundary; never await while holding it.

        Lets a backend publish an already validated, detached dispatch task together
        with reserve(). Does not provide rollback for treatment or consumption.
        """
        with self._lock:
            self._run(run_id)
            yield

    def _resource_snapshot(self, run, resource_id):
        r = run.resources[resource_id]
        initial = r.definition.initial_total
        values = dict(initial_total=initial, received_qty=r.received,
                      consumed_qty=r.consumed, lost_qty=r.lost)
        if initial is None:
            values.update(total_qty=None, available_qty=None, reserved_qty=None,
                          in_use_qty=None, unavailable_qty=None, operational_state='UNKNOWN')
        else:
            total = initial + r.received - r.consumed - r.lost
            counts = Counter()
            for a in run.allocations.values():
                if a.resource_id == resource_id and a.status in ('RESERVED', 'IN_USE', 'QUARANTINED'):
                    counts[a.status] += a.quantity - a.consumed_qty
            free = total - sum(counts.values())
            available = 0 if r.blocked else free
            unavailable = counts['QUARANTINED'] + (free if r.blocked else 0)
            state = r.blocked or ('QUARANTINED' if counts['QUARANTINED'] else
                    'EXHAUSTED' if total == 0 and r.definition.use_mode == 'consumable' else
                    'AVAILABLE' if available == total else 'PARTIALLY_ALLOCATED' if available else
                    'IN_USE' if counts['IN_USE'] else 'RESERVED')
            values.update(total_qty=total, available_qty=available, reserved_qty=counts['RESERVED'],
                          in_use_qty=counts['IN_USE'], unavailable_qty=unavailable, operational_state=state)
        return dict(resource_id=resource_id, resource_type_id=r.definition.resource_type_id,
                    unit=r.definition.unit, use_mode=r.definition.use_mode,
                    location_id=r.location_id, state_version=run.version, updated_at_s=run.at_s, **values)

    def get_snapshot(self, run_id, *, view=None):
        with self._lock:
            run = self._run(run_id)
            ids = run.resources if view is None else run.views[view]
            result = dict(schema_version='301.resource.m2a.1', run_id=run_id, state_version=run.version,
                          at_s=run.at_s, resources={k: self._resource_snapshot(run, k) for k in ids},
                          views=run.views, allocations={k: vars(a) for k, a in run.allocations.items()},
                          locations={k: v.model_dump(mode='json') for k, v in run.locations.items()},
                          plans={k: {'patient_id': p.definition.patient_id, 'actions': p.actions,
                                     'cancelled': p.cancelled} for k, p in run.plans.items()})
            return deepcopy(result)

    def get_events(self, run_id):
        with self._lock:
            return deepcopy(self._run(run_id).events)

    def _conflict(self, run, req, code, detail, *, action=None, resource=None,
                  resource_type=None, needed=None, available=None, unit=None, blockers=()):
        requirement = self._catalog.requirements.get(action.action_type) if action else None
        return Conflict(code=code, run_id=req.run_id, patient_id=req.patient_id, plan_id=req.plan_id,
                        action_instance_id=action.action_instance_id if action else req.action_instance_id,
                        action_type=action.action_type if action else None,
                        requirement_id=requirement.requirement_id if requirement else None,
                        resource_id=resource, resource_type_id=resource_type,
                        required_qty=needed, available_qty=available, unit=unit,
                        blocking_allocation_ids=tuple(blockers), state_version=run.version, detail=detail,
                        evidence_refs=requirement.evidence_refs if requirement else ())

    def _result(self, run, req, conflicts=(), ids=(), affected=()):
        unknown = {'CONSTRAINT_UNKNOWN', 'QUALIFICATION_UNVERIFIED', 'EXECUTION_UNCERTAIN'}
        outcome = ('UNSATISFIED' if any(c.code not in unknown for c in conflicts) else
                   'INDETERMINATE' if conflicts else 'SATISFIED')
        return Result(run_id=req.run_id, patient_id=req.patient_id, plan_id=req.plan_id,
                      request_id=req.request_id, state_version=run.version, outcome=outcome,
                      conflicts=tuple(conflicts), allocation_ids=tuple(ids), affected_allocation_ids=tuple(affected))

    def _conditions(self, run, req, plan):
        conflicts = []
        def add(code, detail, action=None):
            conflicts.append(self._conflict(run, req, code, detail, action=action))
        if (plan.patient_id, plan.plan_id) != (req.patient_id, req.plan_id):
            add('IDENTITY_MISMATCH', 'Request and plan identities differ')
        if plan.scope_kind == 'clinical_design':
            add('QUALIFICATION_UNVERIFIED', 'M1 clinical personnel, equipment and duration requirements remain unconfirmed')
            return conflicts
        invalid = self._catalog.validate_scope(plan)
        if invalid:
            add(*invalid)
            return conflicts
        location = run.locations.get(plan.location_id)
        if location is None:
            add('CONSTRAINT_UNKNOWN' if plan.location_id is None else 'LOCATION_MISMATCH', 'Required location is unknown')
            return conflicts
        for a in plan.actions:
            requirement = self._catalog.requirements[a.action_type]
            for known, wanted, code in [(location.capabilities, a.action_type, 'CAPABILITY_UNAVAILABLE'),
                                        (location.permissions, requirement.permission, 'PROCEDURE_NOT_AUTHORIZED')]:
                if wanted is None:
                    continue
                if known is None:
                    add('CONSTRAINT_UNKNOWN', f'Unknown capability/permission: {wanted}', a)
                elif wanted not in known:
                    add(code, f'Missing capability/permission: {wanted}', a)
            if a.action_type == 'remove_from_exposure':
                for name in ('protected_route_available', 'receiving_environment_verified'):
                    value = getattr(location, name)
                    if value is not True:
                        add('CONSTRAINT_UNKNOWN' if value is None else 'LOCATION_MISMATCH', name, a)
        return conflicts

    def _requirements(self, plan):
        # Reuse within a plan is explicitly sequential: begin requires each predecessor
        # to have accepted execution AND confirmed stopped/cleared usage. Across plans
        # there is no max() sharing. Stock remains a separate allocation per action.
        stock, holds = [], {}
        for a in plan.actions:
            r = self._catalog.requirements[a.action_type]
            stock.extend((key, n, [a]) for key, n in r.stock)
            for key, n in r.holds:
                if key not in holds:
                    holds[key] = [n, []]
                holds[key][0] = max(holds[key][0], n)
                holds[key][1].append(a)
        return stock + [(key, n, actions) for key, (n, actions) in holds.items()]

    def _evaluate(self, run, req, plan):
        errors = self._conditions(run, req, plan)
        for existing in run.plans.values():
            if existing.definition.patient_id != req.patient_id:
                continue
            unfinished = [s for s in existing.actions.values() if s['status'] not in ('FINISHED', 'CANCELLED')]
            if unfinished:
                code = 'EXECUTION_UNCERTAIN' if any(s['execution'] == 'unknown' for s in unfinished) else 'PATIENT_PLAN_ACTIVE'
                errors.append(self._conflict(run, req, code,
                    'Resolve the existing patient plan before reserving another; a new ID cannot replay unknown execution'))
        if errors:
            return errors, []
        chosen, used = [], Counter()
        for kind, quantity, actions in self._requirements(plan):
            unit, mode = self._catalog.resources[kind]
            matches = [(k, r) for k, r in sorted(run.resources.items()) if r.definition.resource_type_id == kind]
            local = [(k, r) for k, r in matches if r.location_id == plan.location_id]
            remaining = quantity
            for rid, r in local:
                count = self._resource_snapshot(run, rid)['available_qty']
                if count is None:
                    continue
                amount = min(remaining, count - used[rid])
                if amount > 0:
                    chosen.append((rid, amount, mode, unit, actions))
                    used[rid] += amount
                    remaining -= amount
                if not remaining:
                    break
            if remaining:
                uncertain = any(r.definition.initial_total is None for _, r in local) or any(r.location_id is None for _, r in matches)
                blockers = [a.allocation_id for a in run.allocations.values()
                            if a.resource_id in dict(local) and a.status in ('RESERVED', 'IN_USE', 'QUARANTINED')]
                code = ('CONSTRAINT_UNKNOWN' if uncertain else 'RESOURCE_IN_USE' if blockers else
                        'RESOURCE_FAULTED' if any(r.blocked for _, r in local) else
                        'LOCATION_MISMATCH' if matches and not local else 'RESOURCE_SHORTAGE')
                errors.append(self._conflict(run, req, code, f'Cannot allocate {kind} at {plan.location_id}',
                              action=actions[0], resource=local[0][0] if len(local) == 1 else None,
                              resource_type=kind, needed=quantity, available=None if uncertain else quantity-remaining,
                              unit=unit, blockers=blockers))
        return errors, chosen

    def evaluate_requirements(self, request, plan):
        req, plan = Request.model_validate(request), Plan.model_validate(plan)
        with self._lock:
            run = self._run(req.run_id)
            if req.expected_state_version != run.version:
                return self._result(run, req, [self._conflict(run, req, 'STALE_SNAPSHOT', 'Snapshot version changed')])
            errors, _ = self._evaluate(run, req, plan)
            return self._result(run, req, errors)

    def _mutate(self, operation, request, payload, handler):
        req = Request.model_validate(request)
        fingerprint = json.dumps({'operation': operation, 'request': req.model_dump(mode='json'),
                                  'payload': payload}, sort_keys=True, allow_nan=False)
        with self._lock:
            current = self._run(req.run_id)
            previous = current.requests.get(req.idempotency_key)
            if previous:
                if previous[0] == fingerprint:
                    return previous[1].model_copy(deep=True)
                return self._result(current, req, [self._conflict(current, req, 'IDEMPOTENCY_CONFLICT', 'Key reused with different operation/request/payload')])
            errors = []
            if req.expected_state_version != current.version:
                errors.append(self._conflict(current, req, 'STALE_SNAPSHOT', 'Snapshot version changed; read current state before a new request'))
            if req.at_s < current.at_s:
                errors.append(self._conflict(current, req, 'TIME_REVERSED', 'Simulation time cannot move backwards'))
            staged = deepcopy(current)
            result = self._result(current, req, errors) if errors else handler(staged, req)
            if result.outcome == 'SATISFIED':
                staged.version += 1
                staged.at_s = req.at_s
                self._assert_invariants(staged)
                self._runs[req.run_id] = staged
                current = staged
                result = result.model_copy(update={'state_version': staged.version})
            current.requests[req.idempotency_key] = (fingerprint, result.model_copy(deep=True))
            current.events.append(dict(event_id=uuid4().hex, operation=operation, request=req.model_dump(mode='json'),
                                       payload=deepcopy(payload), result=result.model_dump(mode='json')))
            return result.model_copy(deep=True)

    def reserve(self, request, plan):
        plan = Plan.model_validate(plan).model_copy(deep=True)
        def apply(run, req):
            if req.action_instance_id is not None:
                return self._result(run, req, [self._conflict(run, req, 'IDENTITY_MISMATCH', 'Whole-plan reservation requires action_instance_id=null')])
            if plan.plan_id in run.plans:
                return self._result(run, req, [self._conflict(run, req, 'PLAN_EXISTS', 'A plan cannot be reserved twice; use original idempotency key')])
            previous_ids = {a for p in run.plans.values() for a in p.actions}
            if previous_ids.intersection(a.action_instance_id for a in plan.actions):
                return self._result(run, req, [self._conflict(run, req, 'IDENTITY_MISMATCH', 'Action instance IDs must be unique across the run')])
            errors, selection = self._evaluate(run, req, plan)
            if errors:
                return self._result(run, req, errors)
            ids = []
            for rid, n, mode, unit, actions in selection:
                aid = uuid4().hex
                run.allocations[aid] = Allocation(aid, req.patient_id, req.plan_id, rid, n, unit, mode,
                    tuple(a.action_instance_id for a in actions),
                    tuple(self._catalog.requirements[a.action_type].requirement_id for a in actions))
                ids.append(aid)
            run.plans[req.plan_id] = PlanState(plan, {a.action_instance_id: {'status': 'RESERVED', 'execution': None}
                                                     for a in plan.actions})
            return self._result(run, req, ids=ids)
        return self._mutate('reserve', request, plan.model_dump(mode='json'), apply)

    def _owned(self, run, req, *, action=True):
        p = run.plans.get(req.plan_id)
        if p is None or p.definition.patient_id != req.patient_id:
            return None, self._conflict(run, req, 'IDENTITY_MISMATCH', 'Unknown plan or wrong patient')
        if action and req.action_instance_id not in p.actions:
            return None, self._conflict(run, req, 'IDENTITY_MISMATCH', 'Action does not belong to plan')
        return p, None

    def begin_usage(self, request):
        def apply(run, req):
            p, error = self._owned(run, req)
            if error:
                return self._result(run, req, [error])
            astate = p.actions[req.action_instance_id]
            if p.cancelled or astate['status'] != 'RESERVED':
                return self._result(run, req, [self._conflict(run, req, 'EXECUTION_UNCERTAIN' if astate['execution'] == 'unknown' else 'ACTION_STATE_CONFLICT', 'Cannot begin cancelled, started or completed action again')])
            errors = self._conditions(run, req, p.definition)
            index = next(i for i, a in enumerate(p.definition.actions) if a.action_instance_id == req.action_instance_id)
            for earlier in p.definition.actions[:index]:
                state = p.actions[earlier.action_instance_id]
                if state['status'] != 'FINISHED' or state['execution'] != 'accepted':
                    errors.append(self._conflict(run, req, 'DEPENDENCY_UNMET', 'Predecessor needs accepted execution and explicit end-of-usage evidence', action=earlier))
            allocations = [a for a in run.allocations.values() if a.plan_id == req.plan_id and req.action_instance_id in a.action_instance_ids]
            for a in allocations:
                r = run.resources[a.resource_id]
                if a.status != 'RESERVED' or r.blocked or r.location_id != p.definition.location_id:
                    code = 'RESOURCE_FAULTED' if r.blocked else 'LOCATION_MISMATCH' if r.location_id != p.definition.location_id else 'RESOURCE_IN_USE'
                    errors.append(self._conflict(run, req, code, 'Reserved resource is no longer usable', resource=a.resource_id, blockers=(a.allocation_id,)))
            if errors:
                # Failure is observational and leaves prior reservations intact; caller may
                # explicitly cancel unused reservations. Never roll back started resources.
                return self._result(run, req, errors)
            for a in allocations:
                a.status, a.active_action_id, a.start_at_s = 'IN_USE', req.action_instance_id, req.at_s
                a.actual_end_at_s = None
            astate['status'] = 'STARTED'
            return self._result(run, req, ids=[a.allocation_id for a in allocations])
        return self._mutate('begin_usage', request, {}, apply)

    def record_consumption(self, request, *, amounts, receipt_ref):
        # Explicit irreversible material event, independent of Pulse acceptance.
        if not isinstance(receipt_ref, str) or not receipt_ref.strip():
            raise ValueError('consumption evidence required')
        if (not isinstance(amounts, dict) or not amounts or
            any(not isinstance(k, str) or not k.strip() for k in amounts) or
            any(type(n) is not int or n <= 0 for n in amounts.values())):
            raise ValueError('positive integer allocation quantities required')
        amounts = deepcopy(amounts)
        def apply(run, req):
            p, error = self._owned(run, req)
            if error:
                return self._result(run, req, [error])
            errors = []
            for aid, n in amounts.items():
                a = run.allocations.get(aid)
                if (a is None or a.plan_id != req.plan_id or a.patient_id != req.patient_id or
                    a.active_action_id != req.action_instance_id or a.use_mode != 'consumable' or
                    a.status not in ('IN_USE', 'QUARANTINED') or n > a.quantity-a.consumed_qty):
                    errors.append(self._conflict(run, req, 'INVALID_CONSUMPTION', 'Not an active owned consumable allocation or quantity exceeds remaining allocation', blockers=(aid,)))
            if errors:
                return self._result(run, req, errors)
            for aid, n in amounts.items():
                a = run.allocations[aid]
                a.consumed_qty += n
                run.resources[a.resource_id].consumed += n
                if a.consumed_qty == a.quantity:
                    a.status = 'CONSUMED'
            return self._result(run, req, ids=amounts)
        return self._mutate('record_consumption', request, {'amounts': amounts, 'receipt_ref': receipt_ref}, apply)

    def record_execution(self, request, execution):
        execution = Execution.model_validate(execution)
        def apply(run, req):
            p, error = self._owned(run, req)
            if error:
                return self._result(run, req, [error])
            s = p.actions[req.action_instance_id]
            if s['status'] not in ('STARTED', 'QUARANTINED') or s['execution'] in ('accepted', 'rejected'):
                return self._result(run, req, [self._conflict(run, req, 'ACTION_STATE_CONFLICT', 'Execution fact requires started action; final receipt cannot be overwritten')])
            s['execution'], s['receipt_ref'] = execution.status, execution.receipt_ref
            if execution.status == 'unknown':
                s['status'] = 'QUARANTINED'
                for a in run.allocations.values():
                    if a.plan_id == req.plan_id and a.active_action_id == req.action_instance_id and a.status == 'IN_USE':
                        a.status = 'QUARANTINED'
            # Accepted/rejected recovery is a new explicit fact; allocations remain
            # quarantined until release evidence. There is never a treatment replay.
            return self._result(run, req)
        return self._mutate('record_execution', request, execution.model_dump(mode='json'), apply)

    def release_unused(self, request, *, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('reason required')
        def apply(run, req):
            p, error = self._owned(run, req, action=False)
            if error:
                return self._result(run, req, [error])
            if req.action_instance_id is not None:
                return self._result(run, req, [self._conflict(run, req, 'IDENTITY_MISMATCH', 'Plan cancellation requires action_instance_id=null')])
            ids = []
            p.cancelled = True
            for s in p.actions.values():
                if s['status'] == 'RESERVED':
                    s['status'] = 'CANCELLED'
            for a in run.allocations.values():
                if a.plan_id == req.plan_id and a.status == 'RESERVED':
                    a.status, a.actual_end_at_s = 'RELEASED', req.at_s
                    ids.append(a.allocation_id)
            return self._result(run, req, ids=ids)
        return self._mutate('release_unused', request, {'reason': reason}, apply)

    def release_usage(self, request, evidence, *, returned_unused_consumables=False):
        evidence = ReleaseEvidence.model_validate(evidence)
        if type(returned_unused_consumables) is not bool:
            raise ValueError('explicit boolean required')
        def apply(run, req):
            p, error = self._owned(run, req)
            if error:
                return self._result(run, req, [error])
            s = p.actions[req.action_instance_id]
            if s['execution'] in (None, 'unknown'):
                return self._result(run, req, [self._conflict(run, req, 'EXECUTION_UNCERTAIN', 'Execution unresolved; no automatic return or replay')])
            if s['status'] not in ('STARTED', 'QUARANTINED'):
                return self._result(run, req, [self._conflict(run, req, 'ACTION_STATE_CONFLICT', 'Action usage already ended or not started')])
            if not (evidence.stopped and evidence.detached and evidence.cleared_for_reuse):
                return self._result(run, req, [self._conflict(run, req, 'CONSTRAINT_UNKNOWN', 'Stop/detach/reuse evidence is incomplete')])
            active = [a for a in run.allocations.values() if a.plan_id == req.plan_id and a.active_action_id == req.action_instance_id]
            if any(a.use_mode == 'consumable' and a.quantity > a.consumed_qty for a in active) and not returned_unused_consumables:
                return self._result(run, req, [self._conflict(run, req, 'CONSTRAINT_UNKNOWN', 'Unconsumed material needs explicit unused-return evidence')])
            for a in active:
                if a.status == 'CONSUMED':
                    a.actual_end_at_s = req.at_s
                    continue
                future = [x for x in a.action_instance_ids if x != req.action_instance_id and p.actions[x]['status'] == 'RESERVED']
                a.status = 'RESERVED' if future and not p.cancelled else 'RELEASED'
                a.active_action_id, a.actual_end_at_s = None, req.at_s
            s['status'] = 'FINISHED'
            return self._result(run, req, ids=[a.allocation_id for a in active])
        return self._mutate('release_usage', request, {'evidence': evidence.model_dump(mode='json'),
                            'returned_unused_consumables': returned_unused_consumables}, apply)

    def record_resource_change(self, request, change):
        change = ResourceChange.model_validate(change)
        def apply(run, req):
            r = run.resources.get(change.resource_id)
            if r is None:
                return self._result(run, req, [self._conflict(run, req, 'RESOURCE_SHORTAGE', 'Unknown canonical resource', resource=change.resource_id)])
            if change.kind == 'move' and change.location_id is not None and change.location_id not in run.locations:
                return self._result(run, req, [self._conflict(run, req, 'LOCATION_MISMATCH', 'Unknown destination')])
            affected = [a for a in run.allocations.values() if a.resource_id == change.resource_id and a.status in ('RESERVED', 'IN_USE', 'QUARANTINED')]
            if change.kind in ('receive', 'lose'):
                snapshot = self._resource_snapshot(run, change.resource_id)
                if snapshot['total_qty'] is None:
                    return self._result(run, req, [self._conflict(run, req, 'CONSTRAINT_UNKNOWN', 'Cannot adjust unknown starting inventory')])
                if change.kind == 'lose' and change.quantity > snapshot['available_qty']:
                    return self._result(run, req, [self._conflict(run, req, 'RESOURCE_IN_USE', 'Loss may only remove unallocated available stock; resolve affected usage first')])
                if change.kind == 'receive':
                    r.received += change.quantity
                else:
                    r.lost += change.quantity
            elif change.kind == 'restore':
                r.blocked = None  # Does not release any quarantined allocation.
            elif change.kind == 'move':
                r.location_id = change.location_id
            else:
                r.blocked = 'FAULTED' if change.kind == 'fault' else 'MAINTENANCE'
                for a in affected:
                    if a.status == 'IN_USE':
                        a.status = 'QUARANTINED'
            return self._result(run, req, affected=[a.allocation_id for a in affected])
        return self._mutate('record_resource_change', request, change.model_dump(mode='json'), apply)

    def record_location_change(self, request, location, *, receipt_ref):
        """Backend capability/permission revocation or revalidation, not an Agent write."""
        location = Location.model_validate(location).model_copy(deep=True)
        if not isinstance(receipt_ref, str) or not receipt_ref.strip():
            raise ValueError('evidence required')
        def apply(run, req):
            if location.location_id not in run.locations:
                return self._result(run, req, [self._conflict(run, req, 'LOCATION_MISMATCH', 'Unknown location')])
            run.locations[location.location_id] = location
            return self._result(run, req)
        return self._mutate('record_location_change', request, {'location': location.model_dump(mode='json'), 'receipt_ref': receipt_ref}, apply)

    def _assert_invariants(self, run):
        for rid, r in run.resources.items():
            s = self._resource_snapshot(run, rid)
            if s['total_qty'] is None:
                if any(a.resource_id == rid for a in run.allocations.values()):
                    raise AssertionError('unknown inventory cannot have allocations')
                continue
            nums = [s[k] for k in ('initial_total', 'received_qty', 'consumed_qty', 'lost_qty',
                                  'total_qty', 'available_qty', 'reserved_qty', 'in_use_qty', 'unavailable_qty')]
            if any(type(n) is not int or n < 0 for n in nums):
                raise AssertionError('negative or non-integer resource accounting')
            if s['initial_total']+s['received_qty']-s['consumed_qty']-s['lost_qty'] != s['total_qty']:
                raise AssertionError('inventory conservation failed')
            if sum(s[k] for k in ('available_qty', 'reserved_qty', 'in_use_qty', 'unavailable_qty')) != s['total_qty']:
                raise AssertionError('allocation conservation failed')
