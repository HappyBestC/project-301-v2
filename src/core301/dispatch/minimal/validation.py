"""Pure deterministic validation. Half-open scheduler intervals [start, end)."""
import copy
import itertools
import math
from collections import defaultdict
from pydantic import ValidationError
from .models import Schedule
from .coverage import accounting, check_results
from .api import requirement
from .personnel_evidence import asset_problems, personnel_overlap_exempt, personnel_evidence

EPS = 1e-8

def validate_schedule(context, proposal):
    conflicts, unchecked, holds, spending, required_care = [], [], [], [], []
    personnel_demands = []
    def issue(code, detail, task=None, resource=None, interval=None, *, unknown=False):
        (unchecked if unknown else conflicts).append({'code':code,'detail':detail,
            'patient_id':getattr(task,'patient_id',None),'task_id':getattr(task,'task_id',None),
            'resource_id':resource,'interval_min':interval})
    try:
        s = Schedule.model_validate(proposal.model_dump() if isinstance(proposal,Schedule) else proposal)
    except (ValidationError,ValueError,TypeError) as exc:
        issue('SCHEMA_INVALID',str(exc))
        return {**accounting(context),'known_constraints_passed':False,'fully_verified':False,'conflicts':conflicts,'unchecked':[],
                'projected_occupancy':[],'projected_inventory_changes':[],'initial_state_mutated':False}
    check_results(context,s,issue)
    r=context['resources']; mapping=context['action_mapping']; horizon=context['horizon_min']
    patients={p['patient_id']:p for p in context['patients']}
    people={p['id']:p for p in r['personnel']}; equipment={e['id']:e for e in r['equipment']}; spaces={p['id']:p for p in r['spaces']}
    vehicles=r['vehicles']; nodes=r['nodes']
    capacities={c['id']:c for c in r.get('service_capacities',[])}
    assets=people|equipment|spaces|capacities
    vehicle_states={vid:{'location':v['location'],'available_from_min':v.get('available_from_min',0)} for vid,v in vehicles.items()}
    actions={a['action_id']:(p,plan,a) for p in patients.values() for plan in p['candidate_plans'] for a in plan['actions']}
    operations={t.task_id:t for t in s.operations}; by_action=defaultdict(list)
    for t in s.operations:by_action[t.action_id].append(t)
    def interval(t):return [t.start_min,t.end_min]
    def hold(resource,start,end,task,kind='operation'):
        if end>start:
            holds.append({'resource_id':resource,'start_min':start,'end_min':end,'patient_id':task.patient_id,'task_id':task.task_id,'kind':kind})
    def usable(asset_id,task,start,end,location,kind='operation'):
        a=assets.get(asset_id)
        if a is None:
            issue('UNKNOWN_RESOURCE','Resource ID not in host inventory',task,asset_id,[start,end]);return
        for code, detail in asset_problems(a,task.patient_id,start,location):
            issue(code,detail,task,asset_id,[start,end])
        hold(asset_id,start,end,task,kind)
    def match_staff(ids,roles,t,start,end):
        personnel_demands.append(dict(task_id=t.task_id,patient_id=t.patient_id,operation_id=getattr(t,'operation_id',None),
                                     location=t.location,start_min=start,end_min=end,roles=list(roles),assigned_ids=list(ids)))
        if len(ids)!=len(roles) or not any(all(role in people.get(pid,{}).get('capabilities',[]) for pid,role in zip(order,roles)) for order in itertools.permutations(ids)):
            issue('STAFF_CAPABILITY_OR_COUNT','Distinct personnel must cover roles '+str(roles),t,','.join(ids),[start,end])
        for pid in ids:
            if pid not in people:issue('NOT_PERSONNEL','Assigned ID is not personnel',t,pid,[start,end])
            usable(pid,t,start,end,t.location)
    trips=defaultdict(list)
    for t in s.transports:
        if t.patient_id not in patients:issue('UNKNOWN_PATIENT','Unknown transported patient',t);continue
        if t.vehicle_id not in vehicles:issue('UNKNOWN_VEHICLE','Unknown vehicle',t,t.vehicle_id);continue
        if t.pickup not in nodes or t.destination not in nodes or t.departure_location not in nodes:
            issue('UNKNOWN_NODE','Unknown route endpoint',t);continue
        trips[t.vehicle_id].append(t)
    all_trips=sorted([t for ts in trips.values() for t in ts],key=lambda t:t.load_start_min)
    def patient_location(pid,time):
        location=patients[pid]['location']
        for t in all_trips:
            if t.patient_id!=pid:continue
            if time<t.load_start_min:break
            if time<t.handoff_end_min:return t.vehicle_id
            location=t.destination
        return location
    for vid,ts in trips.items():
        v=vehicles[vid];location=v['location'];free=v.get('available_from_min',0)
        for t in sorted(ts,key=lambda t:(t.start_min,t.task_id)):
            if v.get('status')!='available':issue('VEHICLE_UNAVAILABLE','Vehicle unavailable',t,vid,interval(t))
            if t.start_min<free-EPS:issue('VEHICLE_OVERLAP','Vehicle still assigned or turning around',t,vid,[t.start_min,free])
            if t.departure_location!=location:issue('VEHICLE_POSITION','Vehicle must depart from its last destination: '+location,t,vid,interval(t))
            travel=r['travel_min'];stages=r['transport_min']
            expected=[t.start_min+travel[location][t.pickup]]
            expected+=[expected[-1]+stages['loading']]
            expected+=[expected[-1]+travel[t.pickup][t.destination]]
            expected+=[expected[-1]+stages['handoff']]
            expected+=[expected[-1]+stages['turnaround']]
            given=[t.load_start_min,t.depart_min,t.arrive_min,t.handoff_end_min,t.end_min]
            if any(abs(a-b)>EPS for a,b in zip(expected,given)):
                issue('TRANSPORT_TIMING','Expected load/depart/arrive/handoff/available='+str(expected),t,vid,interval(t))
            if t.start_min<patients[t.patient_id]['arrival_time_min']:
                issue('BEFORE_ARRIVAL','Patient transport task starts before arrival',t,vid,interval(t))
            # Compute pickup position excluding this trip, with no teleportation.
            previous=[z for z in all_trips if z.patient_id==t.patient_id and z is not t and z.handoff_end_min<=t.load_start_min]
            origin=max(previous,key=lambda z:z.handoff_end_min).destination if previous else patients[t.patient_id]['location']
            if origin!=t.pickup:issue('PATIENT_LOCATION','Pickup does not match patient location '+origin,t,vid,[t.load_start_min,t.depart_min])
            if t.end_min>horizon:issue('OUTSIDE_HORIZON','Transport turnaround exceeds horizon',t,vid,interval(t))
            hold(vid,t.start_min,t.end_min,t,'vehicle')
            stretchers=[z['id'] for z in spaces.values() if z['location']==vid and z['type']=='stretcher']
            if v['stretcher_capacity']!=1 or len(stretchers)!=1:issue('STRETCHER_CONFIG','This document defines one stretcher per vehicle',t,vid)
            else:hold(stretchers[0],t.load_start_min,t.handoff_end_min,t,'transport_space')
            for crew in v['crew']:usable(crew,t,t.start_min,t.end_min,vid,'crew')
            issue('TRANSFER_ELIGIBILITY_UNCHECKED','Transfer/receiving suitability not confirmed; no physiological inference',t,vid,interval(t),unknown=True)
            issue('HANDOFF_REQUIREMENTS_UNCHECKED','Five-minute overall handoff is counted; receiving staff workload and support transfer protocol are not defined',t,vid,[t.arrive_min,t.handoff_end_min],unknown=True)
            location=t.destination;free=t.end_min
        vehicle_states[vid]={'location':location,'available_from_min':free}
    for a,b in itertools.combinations(all_trips,2):
        if a.patient_id==b.patient_id and max(a.load_start_min,b.load_start_min)<min(a.handoff_end_min,b.handoff_end_min):
            issue('PATIENT_TRANSFER_OVERLAP','Patient assigned to two overlapping journeys',b,b.vehicle_id,[max(a.load_start_min,b.load_start_min),min(a.handoff_end_min,b.handoff_end_min)])
    chosen={}
    for pid,planid in s.selections.items():
        plan=next((pl for pl in patients.get(pid,{}).get('candidate_plans',[]) if pl['plan_id']==planid),None)
        if plan is None:issue('UNKNOWN_PLAN','Unknown patient/plan selection '+pid+'/'+planid);continue
        chosen[pid]=plan
        for a in plan['actions']:
            if not any(t.mode=='start' for t in by_action[a['action_id']]):
                conflicts.append({'code':'PLAN_ACTION_MISSING','detail':'Selected plan action not scheduled',
                    'patient_id':pid,'task_id':a['action_id'],'resource_id':None,'interval_min':None})
    requirements={}
    for t in sorted(s.operations,key=lambda t:(t.start_min,t.task_id)):
        if t.action_id not in actions:issue('UNKNOWN_ACTION','Not a host candidate action',t);continue
        patient,plan,a=actions[t.action_id]
        if (t.patient_id,t.plan_id)!=(patient['patient_id'],plan['plan_id']) or s.selections.get(t.patient_id)!=plan['plan_id']:
            issue('PLAN_IDENTITY','Patient/action does not belong to selected plan',t);continue
        k=a['action_type'];rule=requirement(mapping,a,access_mode=t.access_mode,mode=t.mode);requirements[t.task_id]=rule
        if t.start_min<patient['arrival_time_min']:issue('BEFORE_ARRIVAL','Operation before patient arrival',t,interval=interval(t))
        if t.end_min>horizon:issue('OUTSIDE_HORIZON','Operation exceeds horizon',t,interval=interval(t))
        if a['eligibility_status']!='confirmed':
            issue('ELIGIBILITY_PENDING','Candidate suitability is not confirmed',t,unknown=True)
            if not s.demonstration_only:issue('ELIGIBILITY_REQUIRED','Pending plans only allowed as explicit resource demonstrations',t)
        loc_type=nodes.get(t.location,vehicles.get(t.location,{})).get('type')
        allowed=rule['allowed_start'] if t.mode=='start' else rule['allowed_continue']
        if loc_type not in allowed:issue('LOCATION_UNSUPPORTED','Location type cannot perform this action/mode',t,t.location,interval(t))
        boundaries=[t.start_min,t.end_min-EPS]+[point for tr in all_trips if tr.patient_id==t.patient_id for point in (tr.load_start_min,tr.handoff_end_min) if t.start_min<=point<t.end_min]
        if any(patient_location(t.patient_id,time)!=t.location for time in boundaries):
            issue('PATIENT_LOCATION','Patient is not at execution location throughout operation',t,t.location,interval(t))
        if rule['duration_min'] is None:
            issue('CONTINUATION_PROTOCOL_UNCHECKED','Continuation/transfer setup time and consumables are undefined',t,unknown=True)
        elif abs(t.end_min-t.start_min-rule['duration_min'])>EPS:
            issue('ACTION_DURATION','Required operation duration='+str(rule['duration_min']),t,interval=interval(t))
        if t.mode=='start' and sum(z.mode=='start' for z in by_action[t.action_id])!=1:issue('DUPLICATE_ACTION','Action initiation may occur once',t)
        if t.mode=='continue':
            parent=operations.get(t.continuation_of)
            if parent is None or parent.patient_id!=t.patient_id or parent.action_id!=t.action_id or parent.end_min>t.start_min:
                issue('SUPPORT_NOT_ESTABLISHED','Continuation requires the same established support action',t)
            issue('SUPPORT_HANDOFF_UNCHECKED','No verified support handoff/remaining supply protocol',t,unknown=True)
        elif t.continuation_of is not None:issue('INVALID_CONTINUATION','Start operation cannot specify continuation',t)
        for dependency in rule['depends_on']:
            prior=[z for z in by_action[dependency] if z.patient_id==t.patient_id and z.mode=='start']
            if len(prior)!=1 or prior[0].end_min>t.start_min+EPS:
                issue('DEPENDENCY_UNMET','Predecessor must finish: '+dependency,t,dependency,interval(t))
        pred_types=rule['predecessor_actions']+([rule.get('injury_predecessors',{}).get(patient['known_injury_context']['injury_type'])] if rule.get('injury_predecessors',{}).get(patient['known_injury_context']['injury_type']) else [])
        for pred in pred_types:
            if not any(z.patient_id==t.patient_id and z.plan_id==t.plan_id and z.mode=='start' and z.end_min<=t.start_min+EPS and actions.get(z.action_id,(None,None,{}))[2].get('action_type')==pred for z in s.operations):
                issue('DEPENDENCY_UNMET','Mapping requires predecessor type '+pred,t,interval=interval(t))
        access=rule.get('access')
        if access and t.access_mode=='existing':
            fact=r.get('patient_facts',{}).get(t.patient_id,{}).get('iv_access')
            established=isinstance(fact,dict) and fact.get('verified') is True and fact.get('available_from_min',math.inf)<=t.start_min
            established |= any(z.patient_id==t.patient_id and z.task_id!=t.task_id and z.mode=='start' and z.end_min<=t.start_min and 'access' in mapping['actions'].get(actions.get(z.action_id,(None,None,{}))[2].get('action_type'),{}) for z in s.operations)
            if not established:issue('ACCESS_NOT_ESTABLISHED','Existing IV access requires host evidence or a completed access task',t)
        elif not access and (t.access_mode!='new' or t.access_staff_id):issue('UNEXPECTED_ACCESS','Access fields do not apply to this action',t)
        phase=rule['access_phase_min']
        if phase:
            if not t.access_staff_id:issue('ACCESS_STAFF_REQUIRED','New IV access is a separate single-person phase',t)
            else:match_staff([t.access_staff_id],[access['role']],t,t.start_min,t.start_min+phase)
        elif t.access_staff_id:issue('UNEXPECTED_ACCESS_STAFF','No separate access phase required',t,t.access_staff_id)
        match_staff(t.staff_ids,rule['staff_roles'],t,t.start_min+phase,t.end_min)
        if t.consumables!=rule['consumables']:issue('CONSUMABLE_MAPPING_MISMATCH','Consumables must exactly match host mapping '+str(rule['consumables']),t)
        for name,qty in rule['consumables'].items():
            spending.append({'patient_id':t.patient_id,'task_id':t.task_id,'location':t.location,'item':name,'quantity':qty,'at_min':t.start_min if name in access.get('new_consumables',{}) else t.start_min+phase,'kind':'kit'}) if access else spending.append({'patient_id':t.patient_id,'task_id':t.task_id,'location':t.location,'item':name,'quantity':qty,'at_min':t.start_min,'kind':'kit'})
        actual_types=[equipment.get(i,{}).get('type') for i in t.equipment_ids]
        if sorted(str(x) for x in actual_types)!=sorted(rule['equipment']):issue('EQUIPMENT_REQUIREMENT','Equipment types must exactly match '+str(rule['equipment']),t)
        for eid in t.equipment_ids:
            usable(eid,t,t.start_min,horizon if rule['continuous'] else t.end_min+rule['equipment_turnaround_min'],t.location,'support' if rule['continuous'] else 'equipment')
        location_key='vehicle' if t.location in vehicles else loc_type
        allowed_spaces=rule['space_types'].get(location_key,[])
        if allowed_spaces:
            if t.space_id not in spaces or spaces[t.space_id]['type'] not in allowed_spaces:issue('SPACE_REQUIREMENT','Required space types '+str(allowed_spaces),t,t.space_id,interval(t))
            else:
                if rule.get('space_capability'):
                    available=[c for c in capacities.values() if c['location']==t.location and c['type']==rule['space_capability'] and c['requires_space_type']==spaces[t.space_id]['type']]
                    if len(available)!=1:issue('RESEARCH_CAPACITY','A shared research service capacity plus a treatment position is required',t,t.space_id,interval(t))
                    else:usable(available[0]['id'],t,t.start_min,t.end_min,t.location,'service_capacity')
                hold_end=horizon if rule['continuous'] and not t.support_space_id else t.end_min
                # Chest-tube insertion requires treatment then a distinct care position.
                if rule['continuous'] and spaces[t.space_id]['type']=='treatment' and not t.support_space_id:
                    issue('SUPPORT_SPACE_REQUIRED','After insertion select a care position',t,t.space_id)
                usable(t.space_id,t,t.start_min,hold_end,t.location,'space')
        elif t.space_id:issue('UNEXPECTED_SPACE','No space required by this mapping',t,t.space_id)
        if t.support_space_id:
            if not rule['continuous'] or t.support_space_id not in spaces or spaces[t.support_space_id]['type'] not in rule['support_space_types'].get(location_key,[]):
                issue('SUPPORT_SPACE_REQUIREMENT','Unsupported ongoing care position',t,t.support_space_id)
            else:usable(t.support_space_id,t,t.end_min,horizon,t.location,'space')
        if rule['continuous']:
            issue('STOP_CONDITION_UNCHECKED','Support/position release unknown; horizon is accounting truncation, support may continue beyond it; no treatment-end claim',t,interval=[t.end_min,horizon],unknown=True)
            for tr in all_trips:
                if tr.patient_id==t.patient_id and ((tr.load_start_min>=t.end_min and tr.load_start_min<horizon) or (tr.vehicle_id==t.location and t.end_min<=tr.handoff_end_min<horizon)):
                    issue('SUPPORT_HANDOFF_UNCHECKED','Patient moves with ongoing support; no verified handoff/release. Original assets remain reserved.',t,tr.vehicle_id,[tr.load_start_min,tr.handoff_end_min],unknown=True)
            care=rule['care'];due=t.end_min+care['period_min']
            while due<horizon-EPS:
                if due+care['duration_min']>horizon+EPS:
                    issue('CARE_WINDOW_TRUNCATED','Care extends beyond demonstration horizon',t,interval=[due,due+care['duration_min']],unknown=True)
                else:required_care.append({'operation_id':t.task_id,'patient_id':t.patient_id,'start_min':due,'end_min':due+care['duration_min'],'role':care['role']})
                due+=care['period_min']
        for bulk in rule['bulk_resources']:
            if rule.get('bulk_resource_scope',{}).get(bulk)=='out_of_scope_not_modeled_not_zero':
                issue('MV_OXYGEN_OUT_OF_SCOPE','External oxygen consumption is outside this experiment scope, not a verified zero; no oxygen debit',t,bulk,unknown=True)
                continue
            proto=mapping['bulk_protocols'][bulk]
            # A continuation retains the original patient's course supply. The start
            # already projects its delivery to the horizon; handoff remains unchecked.
            if t.mode=='continue' and proto.get('reservation_quantity') is not None:
                continue
            quantity=None;through=horizon;commitment=None
            if proto['rate'] is not None and t.mode=='start':
                quantity=proto['rate']*max(0,horizon-t.end_min)
                if proto['quantity'] is not None:
                    quantity=min(proto['quantity'],quantity)
                    through=min(horizon,t.end_min+proto['quantity']/proto['rate'])
                    commitment=proto.get('reservation_quantity',proto['quantity'])
            if quantity is None:issue('BULK_USAGE_UNCHECKED','Actual use undefined; device setting is not supply consumption',t,bulk,[t.end_min,horizon],unknown=True)
            spending.append({'patient_id':t.patient_id,'task_id':t.task_id,'course_id':t.action_id,
                'location':t.location,'item':bulk,'quantity':quantity,'committed_quantity':commitment,
                'reservation_at_min':t.start_min if commitment is not None else None,
                'at_min':t.end_min,'through_min':through,'kind':'continuous_supply',
                'accounting':'full_course_commitment_consumption_is_part_of_commitment' if commitment is not None else 'projected_integral_not_instantaneous_debit',
                'source_ref':proto.get('source_ref')})
    # Keep a treatment position reserved across a gap to the next same-position action.
    for pid in patients:
        seq=sorted([t for t in s.operations if t.patient_id==pid],key=lambda t:t.start_min)
        for a,b in zip(seq,seq[1:]):
            if a.space_id and a.space_id==b.space_id and a.end_min<b.start_min and not any(t.patient_id==pid and t.load_start_min<b.start_min and t.handoff_end_min>a.end_min for t in all_trips):
                hold(a.space_id,a.end_min,b.start_min,a,'space')
    # Care workload is explicit in the submitted schedule, never free implicit staffing.
    expected={(x['operation_id'],x['start_min'],x['end_min']):x for x in required_care};seen=set()
    for t in s.care:
        key=(t.operation_id,t.start_min,t.end_min);req=expected.get(key)
        if req is None or t.patient_id!=req['patient_id']:
            issue('CARE_TIMING','Care does not match required operation, patient and periodic slot',t,interval=interval(t));continue
        if key in seen:issue('DUPLICATE_CARE','Duplicate care slot',t,interval=interval(t))
        seen.add(key)
        if patient_location(t.patient_id,t.start_min)!=t.location or patient_location(t.patient_id,t.end_min-EPS)!=t.location:
            issue('PATIENT_LOCATION','Care location differs from patient location',t,t.location,interval(t))
        match_staff([t.staff_id],[req['role']],t,t.start_min,t.end_min)
    for key,req in expected.items():
        if key not in seen:issue('CARE_MISSING','Periodic care staff/task missing',operations[req['operation_id']],interval=[req['start_min'],req['end_min']])
    for reservation in r.get('initial_reservations',[]):holds.append(copy.deepcopy(reservation))
    for a,b in itertools.combinations(holds,2):
        lo,hi=max(a['start_min'],b['start_min']),min(a['end_min'],b['end_min'])
        if lo>=hi-EPS:continue
        same_patient=a['patient_id']==b['patient_id']
        if a['resource_id']==b['resource_id']:
            # One patient's existing bed/stretcher is shared, not double counted.
            if same_patient and a['resource_id'] in spaces:continue
            # Crew is reserved for this trip, but may perform this patient's onboard care.
            if personnel_overlap_exempt(a,b):continue
            conflicts.append({'code':'RESOURCE_OVERLAP','detail':'Overlapping reservations','patient_id':b['patient_id'],'task_id':b['task_id'],'resource_id':b['resource_id'],'interval_min':[lo,hi],'blocking_task_id':a['task_id'],'blocking_patient_id':a['patient_id']})
        elif same_patient and a['resource_id'] in spaces and b['resource_id'] in spaces:
            # Ongoing support after transport needs a handoff, never silently release it.
            if a['kind']=='transport_space' or b['kind']=='transport_space':continue
            issue('DOUBLE_POSITION','One patient cannot occupy two care positions simultaneously',operations.get(b['task_id']) or operations.get(a['task_id']),resource=a['resource_id']+','+b['resource_id'],interval=[lo,hi])
    ledger=copy.deepcopy(r['inventory']);changes=[]
    for use in sorted(spending,key=lambda x:(x['at_min'],x['task_id'],x['item'])):
        task=operations[use['task_id']];entry=ledger.get(use['location'],{}).get(use['item'])
        if entry is None:
            issue('INVENTORY_UNDEFINED','No inventory entry',task,use['item'],unknown=True);continue
        before=entry['quantity'];qty=use['quantity'];reserved_before=entry.get('reserved',0)
        commitment=use.get('committed_quantity')
        bound=None
        if before is None or qty is None:
            issue('INVENTORY_UNCHECKED','Missing actual supply inventory or consumption',task,use['location']+':'+use['item'],[use['at_min'],use.get('through_min',use['at_min'])],unknown=True)
            after=None
        else:
            required=commitment if commitment is not None else qty
            if required>before-reserved_before+EPS:
                issue('STOCK_SHORTAGE',f'Need full commitment {required}; available {before-reserved_before}',task,use['location']+':'+use['item'],[use['reservation_at_min'] if use.get('reservation_at_min') is not None else use['at_min'],use.get('through_min',use['at_min'])])
            after=before-qty
            bound=max(0,required-qty) if commitment is not None else 0
            entry['quantity']=after
            entry['reserved']=reserved_before+bound
        changes.append({**use,'before':before,'after':after,'unit':entry['unit'],
            'reserved_before':reserved_before,'patient_bound_remaining':bound,
            'reserved_after':entry.get('reserved',0) if after is not None else None,
            'available_after':after-entry.get('reserved',0) if after is not None else None,
            'checked':before is not None and qty is not None})
    # Deduplicate only exact issue records; no conflicting input records are removed.
    def distinct(items):
        import json
        return list({json.dumps(x,sort_keys=True):x for x in items}.values())
    conflicts,unchecked=distinct(conflicts),distinct(unchecked)
    coverage=accounting(context,s)
    if conflicts:
        coverage['all_patients_scheduled']=False
        coverage['outcome_status']='结果不完整' if not coverage['all_patients_accounted_for'] else '方案仍未通过'
    snapshots = {}
    if not conflicts:
        from .snapshots import snapshot
        for record in holds:
            operation = operations.get(record['task_id'])
            if (operation and record['kind'] in ('space','support') and record['end_min'] == horizon
                    and mapping['actions'][actions[operation.action_id][2]['action_type']]['continuous']):
                record.update(release_status='unknown', end_is_accounting_cutoff=True, may_continue_beyond_horizon=True)
        snapshots = {'observation_summary': snapshot(context,s,holds,changes,context.get('observation_time_min',min(60,horizon))),
                     'planning_summary': snapshot(context,s,holds,changes,horizon)}
    return {**snapshots, **coverage,'known_constraints_passed':not conflicts,'fully_verified':not conflicts and not unchecked,
            'status':'conflicts' if conflicts else 'incomplete_missing_parameters' if unchecked else 'validated',
            'demonstration_only':s.demonstration_only,'conflicts':conflicts,'unchecked':unchecked,
            'personnel_evidence':personnel_evidence(people,personnel_demands,holds,conflicts,EPS),
            'text_reference_hints':[x for x in unchecked if x['code']=='TEXT_REFERENCE_UNVERIFIED'],
            'required_care_tasks':required_care,
            'projected_occupancy':holds if not conflicts else [],
            'projected_inventory_changes':changes if not conflicts else [],
            'projected_vehicle_state':vehicle_states if not conflicts else {},
            'effects_status':'rejected' if conflicts else 'provisional_not_committed' if unchecked else 'validated_projection',
            'initial_state_mutated':False}
