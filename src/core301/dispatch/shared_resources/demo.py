"""Run with PYTHONPATH=src .venv-pulse/bin/python -m core301.dispatch.shared_resources.demo."""
import json
from . import (SharedResourceManager, Plan, Action, Request, Execution, ReleaseEvidence)
from .fixtures import research_scene


def main():
    manager = SharedResourceManager()
    resources, locations = research_scene({'medic': 2, 'airway_kit': 2, 'ventilator': 1})
    manager.create_run('demo-run', resources, locations,
                       views={'facility-view': ['ventilator'], 'team-view': ['ventilator']})
    def plan(patient):
        return Plan(patient_id=patient, plan_id='plan-'+patient, scope_kind='research_fixture',
                    scope_id='respiratory_muscle_impairment', severity=.4, location_id='scene',
                    actions=(Action(action_instance_id=patient+'-int', action_type='intubation'),
                             Action(action_instance_id=patient+'-mv', action_type='mechanical_ventilation')))
    counter = 0
    def request(patient, action=None):
        nonlocal counter
        counter += 1
        return Request(run_id='demo-run', patient_id=patient, plan_id='plan-'+patient,
                       request_id=f'request-{counter}', idempotency_key=f'key-{counter}',
                       action_instance_id=action, at_s=float(counter),
                       expected_state_version=manager.get_snapshot('demo-run')['state_version'])
    def show(label, result=None):
        snapshot = manager.get_snapshot('demo-run')
        print(json.dumps({'step': label, 'result': result.model_dump(mode='json') if result else None,
                          'state_version': snapshot['state_version'], 'resources': snapshot['resources']}, ensure_ascii=False))
    show('initial')
    show('A-read-only-check', manager.evaluate_requirements(request('A'), plan('A')))
    show('A-reserve', manager.reserve(request('A'), plan('A')))
    show('B-conflict', manager.reserve(request('B'), plan('B')))
    show('A-begin-intubation', manager.begin_usage(request('A', 'A-int')))
    snap = manager.get_snapshot('demo-run')
    bags = {k: a['quantity'] for k, a in snap['allocations'].items() if a['resource_id'] == 'airway_kit'}
    show('A-kit-actually-opened', manager.record_consumption(request('A', 'A-int'), amounts=bags, receipt_ref='fixture:kit-opened'))
    show('A-intubation-receipt', manager.record_execution(request('A', 'A-int'), Execution(status='accepted', receipt_ref='fixture:intubation')))
    evidence = ReleaseEvidence(receipt_ref='fixture:confirmed-end-and-cleared', stopped=True, detached=True, cleared_for_reuse=True)
    show('A-end-intubation-resource-use', manager.release_usage(request('A', 'A-int'), evidence))
    show('A-begin-ventilator', manager.begin_usage(request('A', 'A-mv')))
    show('A-ventilator-receipt', manager.record_execution(request('A', 'A-mv'), Execution(status='accepted', receipt_ref='fixture:ventilator-on')))
    show('B-still-conflicts', manager.reserve(request('B'), plan('B')))
    show('A-confirmed-stop-and-release', manager.release_usage(request('A', 'A-mv'), evidence))
    show('B-reserve-after-release', manager.reserve(request('B'), plan('B')))
    show('B-cancel-before-start', manager.release_unused(request('B'), reason='fixture cancellation'))
    # No Pulse is imported or called. These are explicit simulated resource facts.


if __name__ == '__main__':
    main()
