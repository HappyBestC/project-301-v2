"""CompletePlan identity-preserving facade over the existing V2 executor.

Only external RightLeg .4 source control is admitted here. This object stores
identity aliases, never inventory. All resource mutations use M2-A/coordinator.
"""
from core301.contracts.context import ResourceState
from core301.contracts.v2.treatment import TreatmentPlan
from core301.dispatch.complete_contracts import CompletePlan
from core301.dispatch.shared_resources import Request, Execution, ReleaseEvidence


def executor_plan(plan):
    plan = CompletePlan.model_validate(plan)
    if (plan.scope_kind, plan.scope_id, plan.severity) != ('research_fixture', 'external_hemorrhage', .4):
        raise ValueError('Unsupported closed-loop scope')
    if len(plan.actions) != 1 or plan.actions[0].action_type != 'control_external_bleeding':
        raise ValueError('Only the one-action fixed source-control plan is supported')
    # V2 executor command only; original CompletePlan and identity aliases retained.
    # Never downgrade to the legacy eight-action contract.
    return TreatmentPlan(patient_id=plan.patient_id, actions=[{
        'action_type': plan.actions[0].action_type, 'compartment': plan.actions[0].compartment}])


class SharedAuthority:
    authority_kind = 'explicit_research_fixture'

    def __init__(self, plan, coordinator, now, directory):
        self.plan = CompletePlan.model_validate(plan)
        self.command = executor_plan(self.plan)
        self.coordinator = coordinator
        self.manager = coordinator.resources
        self.now = now
        self.directory = directory
        self.task_id = None
        self.runtime_plan_id = None
        self.runtime_action_id = None
        self.sequence = 0
        self.events = []
        self.last_receipt = None

    def request(self, operation, action=False):
        self.sequence += 1
        key = f'{self.plan.plan_id}:{operation}:{self.sequence}'
        return Request(run_id=self.plan.run_id, patient_id=self.plan.patient_id,
            plan_id=self.plan.plan_id, request_id=key, idempotency_key=key,
            action_instance_id=self.plan.actions[0].action_instance_id if action else None,
            at_s=float(self.now()), expected_state_version=self.manager.get_snapshot(self.plan.run_id)['state_version'])

    @staticmethod
    def require(result):
        if result.outcome != 'SATISFIED':
            raise RuntimeError(str(result.model_dump(mode='json')))
        return result

    def note(self, state, **data):
        event = dict(run_id=self.plan.run_id, patient_id=self.plan.patient_id,
            plan_id=self.plan.plan_id, action_instance_id=self.plan.actions[0].action_instance_id,
            simulation_time_s=float(self.now()), state=state, **data)
        self.events.append(event)
        import json
        with (self.directory/'execution_events.jsonl').open('a') as f:
            f.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n')
        return event

    def snapshot(self, run_id, patient_id):
        if (run_id, patient_id) != (self.plan.run_id, self.plan.patient_id):
            raise ValueError('Resource identity mismatch')
        s = self.manager.get_snapshot(run_id)['resources'].get('medic', {})
        return ResourceState(**{k: (s.get('available_qty', 0) if k == 'medic' else 0)
                               for k in ResourceState.model_fields})

    def reserve(self, plan_id, plan, run_id, patient_id):
        if (run_id, patient_id) != (self.plan.run_id, self.plan.patient_id) or plan != self.command:
            raise ValueError('Executor command differs from complete plan')
        if self.runtime_plan_id is not None or self.task_id is None:
            raise ValueError('No confirmed dispatch or executor binding already used')
        snapshot = self.manager.get_snapshot(run_id)
        allocations = {k:v for k,v in snapshot['allocations'].items()
                       if v['plan_id']==self.plan.plan_id and v['patient_id']==patient_id}
        if not allocations or any(v['status']!='RESERVED' for v in allocations.values()):
            raise ValueError('Shared reservation missing or no longer reserved')
        self.runtime_plan_id = plan_id
        self.note('RESERVED', runtime_plan_id=plan_id, allocation_ids=list(allocations))
        return {'authority_kind':self.authority_kind, 'shared_plan_id':self.plan.plan_id,
                'allocation_ids':list(allocations), 'production_inventory':False}

    def begin(self, plan_id, action_id, action_type):
        if plan_id != self.runtime_plan_id or action_type != self.plan.actions[0].action_type or self.runtime_action_id is not None:
            raise ValueError('Executor action identity/replay mismatch')
        result = self.require(self.coordinator.begin_usage(self.request('begin', True), self.task_id))
        self.runtime_action_id = action_id
        self.note('STARTED', runtime_action_id=action_id, allocation_ids=list(result.allocation_ids))
        return {'allocated_units':{}, 'allocation_ids':list(result.allocation_ids),
                'action_instance_id':self.plan.actions[0].action_instance_id,
                'consumption':'no stock requirement for this research proxy'}

    def acknowledge(self, plan_id, action_id, accepted):
        if (plan_id, action_id) != (self.runtime_plan_id, self.runtime_action_id):
            raise ValueError('Native receipt identity mismatch')
        status = 'accepted' if accepted is True else 'rejected' if accepted is False else 'unknown'
        event = self.note('EXECUTION_'+status.upper(), runtime_action_id=action_id,
                          source='CaseRuntime native action result', accepted=accepted)
        ref = str(self.directory/'execution_events.jsonl')+f'#event={len(self.events)}'
        self.require(self.manager.record_execution(self.request('receipt', True), Execution(status=status, receipt_ref=ref)))
        self.last_receipt = event

    def release_unused(self, plan_id):
        # Existing executor invokes this on failure. Only RESERVED allocations return.
        self.require(self.manager.release_unused(self.request('unused'), reason='executor failure; active/unknown retained'))

    def finish(self, record):
        if record['status'] != 'COMPLETED' or len(record['actions']) != 1:
            raise ValueError('No native completed source-control evidence')
        item = record['actions'][0]
        if item['accepted'] is not True or not item.get('delivery',{}).get('source_control_confirmed'):
            raise ValueError('No confirmed source-control mechanism')
        if item['action_id'] != self.runtime_action_id:
            raise ValueError('Completion identity mismatch')
        # This proxy has no persistent device or consumable. Personnel token use
        # ends at native-confirmed source removal, not on close()/accepted alone.
        ref = str(self.directory/'runtime/execution_journal.json')
        self.note('USAGE_END_EVIDENCE', source=ref, interpretation='research proxy finished; no device attached; medic token reusable')
        self.require(self.manager.release_usage(self.request('release', True), ReleaseEvidence(
            receipt_ref=ref, stopped=True, detached=True, cleared_for_reuse=True)))
        self.note('RELEASED', source=ref)

    def audit(self):
        return self.manager.get_snapshot(self.plan.run_id)

    def close_case(self):
        # Closing Pulse is not evidence of stopped equipment or known execution.
        pass


class CompleteExecutionBridge:
    def __init__(self, runtime, authority):
        self.runtime, self.authority = runtime, authority
        self.bound = None

    def execute(self, plan, *, request_id, context_ref):
        plan = CompletePlan.model_validate(plan)
        if plan != self.authority.plan:
            raise ValueError('CompletePlan changed after registration')
        command = executor_plan(plan)
        binding = (request_id, context_ref)
        if self.bound is not None and binding != self.bound:
            raise ValueError('One execution episode; query original request, no retry')
        self.bound = binding  # An uncertain call cannot be resubmitted under a new ID.
        return self.runtime.execute_plan(command, request_id=request_id, context_ref=context_ref)
