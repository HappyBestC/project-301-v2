from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import copy
import json
import math
import pytest
from pydantic import ValidationError

from core301.dispatch.shared_resources import (
    SharedResourceManager, Action, Plan, Request, Resource, Location, Execution,
    ReleaseEvidence, ResourceChange)
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_resources.catalog import Catalog


class Harness:
    def __init__(self, counts=None):
        self.manager = SharedResourceManager()
        self.resources, self.locations = research_scene(counts if counts is not None else
            {'medic': 2, 'airway_kit': 3, 'ventilator': 1, 'saline_500ml_bag': 2, 'blood_500ml_bag': 1})
        self.manager.create_run('r', self.resources, self.locations,
                                views={'facility': ['ventilator']} if 'ventilator' in [r.resource_id for r in self.resources] else {})
        self.n = 0

    def req(self, plan, action=None, *, run='r', version=None, key=None, at=None):
        self.n += 1
        return Request(run_id=run, patient_id=plan.patient_id, plan_id=plan.plan_id,
            request_id=f'req-{self.n}', idempotency_key=key or f'key-{self.n}', action_instance_id=action,
            at_s=float(self.n) if at is None else at,
            expected_state_version=self.manager.get_snapshot(run)['state_version'] if version is None else version)

    def snapshot(self, run='r'):
        s = self.manager.get_snapshot(run)
        for r in s['resources'].values():
            if r['total_qty'] is None:
                continue
            assert r['initial_total']+r['received_qty']-r['consumed_qty']-r['lost_qty'] == r['total_qty']
            assert sum(r[k] for k in ('available_qty','reserved_qty','in_use_qty','unavailable_qty')) == r['total_qty']
            assert all(type(r[k]) is int and r[k] >= 0 for k in ('total_qty','available_qty','reserved_qty','in_use_qty','unavailable_qty','consumed_qty'))
        return s


def ventilation(patient='A'):
    return Plan(patient_id=patient, plan_id='plan-'+patient, scope_kind='research_fixture',
                scope_id='respiratory_muscle_impairment', severity=.4, location_id='scene',
                actions=(Action(action_instance_id=patient+'-int', action_type='intubation'),
                         Action(action_instance_id=patient+'-mv', action_type='mechanical_ventilation')))


def fluid(patient='A'):
    return Plan(patient_id=patient, plan_id='plan-'+patient, scope_kind='research_fixture',
                scope_id='dehydration', severity=.4, location_id='scene',
                actions=(Action(action_instance_id=patient+'-fluid', action_type='fluid_resuscitation'),))


def good(result):
    assert result.outcome == 'SATISFIED', result.model_dump()
    return result


def codes(result):
    return {c.code for c in result.conflicts}


def release_evidence():
    return ReleaseEvidence(receipt_ref='fixture:stop-and-clean', stopped=True, detached=True, cleared_for_reuse=True)


def begin(h, p, action):
    return good(h.manager.begin_usage(h.req(p, action)))


def accept(h, p, action, status='accepted'):
    return good(h.manager.record_execution(h.req(p, action), Execution(status=status, receipt_ref='fixture:receipt')))


def end(h, p, action, **kw):
    return good(h.manager.release_usage(h.req(p, action), release_evidence(), **kw))


def consume(h, p, action):
    amounts = {k: a['quantity']-a['consumed_qty'] for k,a in h.snapshot()['allocations'].items()
               if a['active_action_id']==action and a['use_mode']=='consumable' and a['status']=='IN_USE'}
    return good(h.manager.record_consumption(h.req(p, action), amounts=amounts, receipt_ref='fixture:opened'))


def test_sufficient_and_readonly_evaluation():
    h=Harness(); p=ventilation(); before=h.snapshot(); events=h.manager.get_events('r')
    good(h.manager.evaluate_requirements(h.req(p),p))
    assert h.snapshot()==before and h.manager.get_events('r')==events
    result=good(h.manager.reserve(h.req(p),p)); assert len(result.allocation_ids)==3
    s=h.snapshot(); assert s['resources']['ventilator']['reserved_qty']==1
    assert s['resources']['ventilator']['available_qty']==0


def test_insufficient_and_structured_conflict():
    h=Harness({'medic':1,'airway_kit':1,'ventilator':0}); p=ventilation()
    before=h.snapshot(); result=h.manager.reserve(h.req(p),p)
    assert 'RESOURCE_SHORTAGE' in codes(result)
    c=result.conflicts[0]
    assert (c.run_id,c.patient_id,c.plan_id,c.resource_type_id,c.required_qty,c.available_qty,c.unit,c.state_version)==('r','A','plan-A','ventilator',1,0,'device',0)
    assert c.evidence_refs and c.requirement_id and c.action_instance_id
    assert h.snapshot()==before


def test_atomic_group_does_not_leak_first_resources():
    h=Harness({'medic':1,'airway_kit':0,'ventilator':1});p=ventilation()
    before=h.snapshot(); assert h.manager.reserve(h.req(p),p).outcome=='UNSATISFIED'
    assert h.snapshot()==before
    assert not h.snapshot()['allocations']


def test_thread_race_only_one_winner():
    h=Harness(); a,b=ventilation('A'),ventilation('B'); barrier=Barrier(2)
    requests=[h.req(a,version=0,at=1.0),h.req(b,version=0,at=1.0)]
    def reserve(pair):
        req,p=pair;barrier.wait();return h.manager.reserve(req,p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(reserve,zip(requests,[a,b])))
    assert [r.outcome for r in results].count('SATISFIED')==1
    assert any('STALE_SNAPSHOT' in codes(r) for r in results)
    assert h.snapshot()['resources']['ventilator']['reserved_qty']==1
    loser=a if results[0].outcome!='SATISFIED' else b
    result=h.manager.reserve(h.req(loser),loser)
    assert 'RESOURCE_IN_USE' in codes(result) and result.conflicts[0].blocking_allocation_ids


def test_cancel_then_other_patient_can_reserve():
    h=Harness();a,b=ventilation('A'),ventilation('B')
    good(h.manager.reserve(h.req(a),a));good(h.manager.release_unused(h.req(a),reason='cancelled'))
    assert h.snapshot()['resources']['ventilator']['available_qty']==1
    good(h.manager.reserve(h.req(b),b));h.snapshot()


def test_actual_consumption_not_acceptance_and_no_rollback():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid');accept(h,p,'A-fluid')
    assert h.snapshot()['resources']['saline_500ml_bag']['consumed_qty']==0
    consume(h,p,'A-fluid');good(h.manager.release_unused(h.req(p),reason='task failed'))
    assert h.snapshot()['resources']['saline_500ml_bag']['total_qty']==1
    end(h,p,'A-fluid')
    assert h.snapshot()['resources']['saline_500ml_bag']['consumed_qty']==1
    assert h.snapshot()['resources']['medic']['available_qty']==2


def test_persistent_ventilator_requires_explicit_release():
    h=Harness();p=ventilation();good(h.manager.reserve(h.req(p),p))
    assert 'DEPENDENCY_UNMET' in codes(h.manager.begin_usage(h.req(p,'A-mv')))
    begin(h,p,'A-int');consume(h,p,'A-int');accept(h,p,'A-int');end(h,p,'A-int')
    begin(h,p,'A-mv');accept(h,p,'A-mv')
    good(h.manager.release_unused(h.req(p),reason='plan completed'))
    assert h.snapshot()['resources']['ventilator']['in_use_qty']==1
    bad=release_evidence().model_copy(update={'stopped':False})
    assert h.manager.release_usage(h.req(p,'A-mv'),bad).outcome=='INDETERMINATE'
    end(h,p,'A-mv');assert h.snapshot()['resources']['ventilator']['available_qty']==1


def test_unknown_quarantines_without_restore_or_replay():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid');consume(h,p,'A-fluid');accept(h,p,'A-fluid','unknown')
    good(h.manager.release_unused(h.req(p),reason='timeout'))
    s=h.snapshot();assert s['resources']['medic']['unavailable_qty']==1
    assert s['resources']['saline_500ml_bag']['consumed_qty']==1
    assert 'EXECUTION_UNCERTAIN' in codes(h.manager.release_usage(h.req(p,'A-fluid'),release_evidence()))
    assert 'EXECUTION_UNCERTAIN' in codes(h.manager.begin_usage(h.req(p,'A-fluid')))
    accept(h,p,'A-fluid','rejected');end(h,p,'A-fluid')
    assert h.snapshot()['resources']['medic']['available_qty']==2


def test_rejected_without_consumption_needs_return_evidence():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid');accept(h,p,'A-fluid','rejected')
    assert h.manager.release_usage(h.req(p,'A-fluid'),release_evidence()).outcome=='INDETERMINATE'
    end(h,p,'A-fluid',returned_unused_consumables=True)
    assert h.snapshot()['resources']['saline_500ml_bag']['total_qty']==2


def test_idempotency_and_conflicting_keys():
    h=Harness();p=fluid();req=h.req(p);result=good(h.manager.reserve(req,p));before=h.snapshot()
    assert h.manager.reserve(req,p)==result and h.snapshot()==before
    assert 'IDEMPOTENCY_CONFLICT' in codes(h.manager.reserve(req,fluid('B')))
    begin(h,p,'A-fluid')
    aid=next(k for k,a in h.snapshot()['allocations'].items() if a['use_mode']=='consumable')
    req=h.req(p,'A-fluid');res=good(h.manager.record_consumption(req,amounts={aid:1},receipt_ref='opened'))
    before=h.snapshot()
    assert h.manager.record_consumption(req,amounts={aid:1},receipt_ref='opened')==res
    assert h.snapshot()==before
    assert 'IDEMPOTENCY_CONFLICT' in codes(h.manager.record_consumption(req,amounts={aid:2},receipt_ref='opened'))
    assert 'INVALID_CONSUMPTION' in codes(h.manager.record_consumption(h.req(p,'A-fluid'),amounts={aid:1},receipt_ref='new event'))


def test_fault_restore_move_and_version():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));old=h.req(p,'A-fluid')
    good(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='medic',kind='fault',reason='fault',receipt_ref='event')))
    assert 'STALE_SNAPSHOT' in codes(h.manager.begin_usage(old))
    assert 'RESOURCE_FAULTED' in codes(h.manager.begin_usage(h.req(p,'A-fluid')))
    good(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='medic',kind='restore',reason='fixed',receipt_ref='event')))
    good(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='medic',kind='move',location_id=None,reason='unknown location',receipt_ref='event')))
    assert 'LOCATION_MISMATCH' in codes(h.manager.begin_usage(h.req(p,'A-fluid')))
    h.snapshot()


def test_two_runs_isolated_and_duplicate_run_rejected():
    h=Harness();h.manager.create_run('r2',h.resources,h.locations);p=ventilation()
    good(h.manager.reserve(h.req(p),p));good(h.manager.reserve(h.req(p,run='r2'),p))
    good(h.manager.release_unused(h.req(p),reason='cancelled'))
    assert h.snapshot('r')['resources']['ventilator']['available_qty']==1
    assert h.snapshot('r2')['resources']['ventilator']['available_qty']==0
    with pytest.raises(ValueError):h.manager.create_run('r',h.resources,h.locations)


@pytest.mark.parametrize('unknown', ['clinical','quantity','location','capability','permission'])
def test_unknown_is_never_available(unknown):
    h=Harness({'medic':1,'saline_500ml_bag':None} if unknown=='quantity' else None);p=fluid()
    if unknown=='clinical':p=p.model_copy(update={'scope_kind':'clinical_design'})
    if unknown=='location':p=p.model_copy(update={'location_id':None})
    if unknown in ('capability','permission'):
        loc=h.locations[0].model_copy(update={'capabilities' if unknown=='capability' else 'permissions':None})
        good(h.manager.record_location_change(h.req(p),loc,receipt_ref='unverified'))
    before=h.snapshot();result=h.manager.reserve(h.req(p),p)
    assert result.outcome=='INDETERMINATE';assert h.snapshot()==before


def test_views_reference_same_inventory_and_detached_snapshots():
    h=Harness();p=ventilation()
    h.manager.create_run('views',h.resources,h.locations,views={'team':['ventilator'],'facility':['ventilator']})
    good(h.manager.reserve(h.req(p,run='views'),p))
    a=h.manager.get_snapshot('views',view='team');b=h.manager.get_snapshot('views',view='facility')
    assert a['resources']==b['resources']
    a['resources']['ventilator']['available_qty']=99
    a['allocations'].clear()
    assert h.manager.get_snapshot('views',view='team')==b
    with pytest.raises(ValueError):h.manager.create_run('dup',h.resources+[h.resources[0]],h.locations)


@pytest.mark.parametrize('qty',[-1,True,1.5,float('nan'),float('inf'),'1'])
def test_invalid_quantities_rejected(qty):
    with pytest.raises(ValidationError):research_scene({'ventilator':qty})


@pytest.mark.parametrize('time',[True,-1,float('nan'),float('inf'),'1'])
def test_invalid_times_rejected(time):
    h=Harness()
    with pytest.raises(ValidationError):h.req(fluid(),at=time)


def test_no_time_reversal_or_implicit_wallclock_expiry():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p,at=20.0),p))
    assert 'TIME_REVERSED' in codes(h.manager.begin_usage(h.req(p,'A-fluid',at=19.0)))
    assert h.snapshot()['resources']['medic']['reserved_qty']==1


def test_received_lost_conservation_and_over_loss_atomic():
    h=Harness();p=fluid()
    for kind,n in [('receive',3),('lose',2)]:
        good(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='saline_500ml_bag',kind=kind,quantity=n,reason=kind,receipt_ref='event')))
        h.snapshot()
    before=h.snapshot()
    assert 'RESOURCE_IN_USE' in codes(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='saline_500ml_bag',kind='lose',quantity=99,reason='bad',receipt_ref='event')))
    assert h.snapshot()==before


def test_permission_revocation_at_begin():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p))
    loc=h.locations[0].model_copy(update={'permissions':frozenset()})
    good(h.manager.record_location_change(h.req(p),loc,receipt_ref='revoked'))
    assert 'PROCEDURE_NOT_AUTHORIZED' in codes(h.manager.begin_usage(h.req(p,'A-fluid')))
    assert h.snapshot()['resources']['saline_500ml_bag']['consumed_qty']==0


def test_bad_scope_targets_and_disabled_action():
    h=Harness();p=fluid()
    for modified in [p.model_copy(update={'scope_id':'invented'}),p.model_copy(update={'severity':.5}),
                     p.model_copy(update={'actions':(Action(action_instance_id='X',action_type='inhaled_albuterol'),)})]:
        assert h.manager.reserve(h.req(modified),modified).outcome!='SATISFIED'
    p=Plan(patient_id='A',plan_id='p',scope_kind='research_fixture',scope_id='open_pneumothorax',severity=.6,location_id='scene',
           actions=(Action(action_instance_id='a',action_type='occlusive_dressing',side='Right'),))
    assert 'DEPENDENCY_UNMET' in codes(h.manager.reserve(h.req(p),p))


def test_catalog_coverage_and_composite_sequential_reuse():
    c=Catalog();assert len(c.requirements)==12 and 'inhaled_albuterol' not in c.requirements
    h=Harness({k:3 for k in c.resources})
    for i,(scope,profile) in enumerate(c.composites.items()):
        kinds=profile['treatment_bundles']['A']+profile['treatment_bundles']['B']
        actions=tuple(Action(action_instance_id=f'{i}-{j}',action_type=k,
                      side='Left' if k in ('occlusive_dressing','needle_decompression','chest_tube','control_hemothorax_bleeding') else None,
                      compartment={'control_external_bleeding':'RightLeg','control_internal_bleeding':'Spleen'}.get(k)) for j,k in enumerate(kinds))
        p=Plan(patient_id=f'P{i}',plan_id=f'plan{i}',scope_kind='research_fixture',scope_id=scope,location_id='scene',actions=actions)
        good(h.manager.reserve(h.req(p),p))
        # Entire ordered plan can reuse medic only after explicit predecessor completion.
        for a in actions:
            begin(h,p,a.action_instance_id)
            if any(a['active_action_id']==a_id and a['use_mode']=='consumable' and a['status']=='IN_USE'
                   for a_id in [a.action_instance_id] for a in h.snapshot()['allocations'].values()):
                consume(h,p,a.action_instance_id)
            accept(h,p,a.action_instance_id);end(h,p,a.action_instance_id)
        h.snapshot()


def test_wrong_patient_and_duplicate_action_ids():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p))
    req=h.req(p,'A-fluid').model_copy(update={'patient_id':'intruder'})
    assert 'IDENTITY_MISMATCH' in codes(h.manager.begin_usage(req))
    duplicate=fluid('B').model_copy(update={'actions':p.actions})
    assert 'IDENTITY_MISMATCH' in codes(h.manager.reserve(h.req(duplicate),duplicate))


def test_fault_during_usage_does_not_free_after_restore():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid')
    for kind in ['fault','restore']:
        good(h.manager.record_resource_change(h.req(p),ResourceChange(resource_id='medic',kind=kind,reason=kind,receipt_ref='event')))
    assert h.snapshot()['resources']['medic']['unavailable_qty']==1
    accept(h,p,'A-fluid');end(h,p,'A-fluid',returned_unused_consumables=True)
    assert h.snapshot()['resources']['medic']['available_qty']==2


def test_failed_request_is_idempotent_and_events_are_detached():
    h=Harness({'medic':0,'saline_500ml_bag':0});p=fluid();req=h.req(p)
    r=h.manager.reserve(req,p);n=len(h.manager.get_events('r'))
    assert h.manager.reserve(req,p)==r and len(h.manager.get_events('r'))==n
    events=h.manager.get_events('r');events[0]['result']['outcome']='forged'
    assert h.manager.get_events('r')[0]['result']['outcome']=='UNSATISFIED'


def test_invalid_mutation_is_atomic_and_no_import_of_native_engine():
    import sys
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid')
    aid=next(k for k,a in h.snapshot()['allocations'].items() if a['use_mode']=='consumable')
    before=h.snapshot()
    result=h.manager.record_consumption(h.req(p,'A-fluid'),amounts={aid:1,'bad':1},receipt_ref='event')
    assert result.outcome=='UNSATISFIED' and h.snapshot()==before
    assert not any(k.startswith('pulse.engine') for k in sys.modules)


def test_new_plan_id_cannot_bypass_unknown_execution():
    h=Harness();p=fluid();good(h.manager.reserve(h.req(p),p));begin(h,p,'A-fluid');accept(h,p,'A-fluid','unknown')
    next_plan=p.model_copy(update={'plan_id':'next','actions':(Action(action_instance_id='next-action',action_type='fluid_resuscitation'),)})
    assert 'EXECUTION_UNCERTAIN' in codes(h.manager.reserve(h.req(next_plan),next_plan))
    good(h.manager.release_unused(h.req(p),reason='timeout'))
    assert 'EXECUTION_UNCERTAIN' in codes(h.manager.reserve(h.req(next_plan),next_plan))


def test_many_threads_same_idempotency_key_only_one_allocation():
    h=Harness();p=fluid();req=h.req(p)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:h.manager.reserve(req,p),range(24)))
    assert all(r==results[0] for r in results)
    assert h.snapshot()['state_version']==1 and len(h.snapshot()['allocations'])==2
    assert len(h.manager.get_events('r'))==1


def test_all_twelve_mappings_are_exercised_in_admitted_single_scopes():
    c=Catalog();covered=set()
    for i,(scope,profile) in enumerate(c.singles.items()):
        choices=[profile['actions']]
        if 'transfusion' in profile['actions']:
            # Existing contract forbids fluid and blood in the same plan.
            choices=[[k for k in profile['actions'] if k!='transfusion'],
                     [k for k in profile['actions'] if k!='fluid_resuscitation']]
        for j,kinds in enumerate(choices):
            h=Harness({k:2 for k in c.resources})
            # The frozen whitelist is not ordered; use the existing required order.
            kinds=sorted(kinds,key=lambda k: 0 if k.startswith('control_') or k=='intubation' else 1)
            actions=tuple(Action(action_instance_id=f'{i}-{j}-{n}',action_type=k,
                side='Left' if k in ('occlusive_dressing','needle_decompression','chest_tube','control_hemothorax_bleeding') else None,
                compartment={'control_external_bleeding':'RightLeg','control_internal_bleeding':'Spleen'}.get(k)) for n,k in enumerate(kinds))
            p=Plan(patient_id='P',plan_id='p',scope_kind='research_fixture',scope_id=scope,
                   severity=profile.get('severity_levels',[None])[0],location_id='scene',actions=actions)
            good(h.manager.reserve(h.req(p),p));covered.update(kinds);h.snapshot()
    assert covered==set(c.requirements)


def test_resource_unit_mode_and_unknown_view_validation():
    h=Harness()
    for updates in [{'unit':'mL'},{'use_mode':'consumable'},{'resource_type_id':'invented'}]:
        modified=h.resources[0].model_copy(update=updates)
        with pytest.raises(ValueError):h.manager.create_run('bad',[modified],h.locations)
    with pytest.raises(ValueError):h.manager.create_run('bad',h.resources,h.locations,views={'team':['absent']})


def test_conflicting_actions_and_unpaired_ventilation_rejected():
    h=Harness();p=Plan(patient_id='A',plan_id='p',scope_kind='research_fixture',scope_id='external_hemorrhage',severity=.4,location_id='scene',
                      actions=(Action(action_instance_id='f',action_type='fluid_resuscitation'),Action(action_instance_id='b',action_type='transfusion')))
    assert 'DEPENDENCY_UNMET' in codes(h.manager.reserve(h.req(p),p))
    p=ventilation().model_copy(update={'actions':(ventilation().actions[-1],)})
    assert 'DEPENDENCY_UNMET' in codes(h.manager.reserve(h.req(p),p))


def test_mutated_pydantic_instance_is_revalidated():
    h=Harness();p=fluid();bad=h.req(p).model_copy(update={'at_s':float('nan')})
    with pytest.raises(ValidationError):h.manager.reserve(bad,p)


def test_cancellation_of_partial_sequence_frees_unused_not_consumed():
    h=Harness();p=ventilation();good(h.manager.reserve(h.req(p),p))
    begin(h,p,'A-int');consume(h,p,'A-int');accept(h,p,'A-int','rejected')
    good(h.manager.release_unused(h.req(p),reason='intubation failed'))
    s=h.snapshot();assert s['resources']['ventilator']['available_qty']==1
    assert s['resources']['airway_kit']['consumed_qty']==1
    assert s['resources']['medic']['in_use_qty']==1
    end(h,p,'A-int');assert h.snapshot()['resources']['medic']['available_qty']==2
    assert 'ACTION_STATE_CONFLICT' in codes(h.manager.begin_usage(h.req(p,'A-mv')))


def test_sequential_personnel_reuse_resets_current_usage_end_time():
    h=Harness();p=Plan(patient_id='A',plan_id='p',scope_kind='research_fixture',scope_id='external_hemorrhage',severity=.4,location_id='scene',
        actions=(Action(action_instance_id='stop',action_type='control_external_bleeding',compartment='RightLeg'),
                 Action(action_instance_id='fluid',action_type='fluid_resuscitation')))
    good(h.manager.reserve(h.req(p),p));begin(h,p,'stop');accept(h,p,'stop');end(h,p,'stop')
    begin(h,p,'fluid')
    medic=next(a for a in h.snapshot()['allocations'].values() if a['resource_id']=='medic')
    assert medic['status']=='IN_USE' and medic['active_action_id']=='fluid' and medic['actual_end_at_s'] is None
