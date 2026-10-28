"""Host-owned configuration, sanitized input, task requirements and Agent bridge."""
import copy
import hashlib
import json
import math
from pathlib import Path
from core301.paths import PROJECT_ROOT
from core301.observation_candidate_v2.models import PatientObservationV2
from core301.observation_candidate_v2.projector import Access, project
from .models import Schedule

CONFIG = PROJECT_ROOT / 'config/medical_resources_v1'
DATASET = PROJECT_ROOT / 'dataset_v1/run_001'

def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))

def load_config(directory=CONFIG):
    resources, mapping = read(directory/'resources.json'), read(directory/'actions.json')
    for path, expected in resources['source_sha256'].items():
        if hashlib.sha256((PROJECT_ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Document changed; review configuration: {path}')
    for protocol in mapping['bulk_protocols'].values():
        if 'source_sha256' in protocol:
            if hashlib.sha256((PROJECT_ROOT/protocol['source_ref']).read_bytes()).hexdigest() != protocol['source_sha256']:
                raise ValueError('Fixed protocol source changed')
    return resources, mapping

def load_cases(dataset=DATASET):
    """Use structured source; do not read or publish backend physiology/Severity."""
    specs = {s['patient_id']: s for s in read(dataset/'patient_specs.json')}
    plans = read(dataset/'action_plan_templates.json')
    index = read(dataset/'patients_initial.json')
    target_rules = read(CONFIG/'actions.json')['actions']
    if set(specs) != {f'P{i:02}' for i in range(1, 17)} or {r['patient_id'] for r in index} != set(specs) or len(index) != 16:
        raise ValueError('Expected P01–P16 exactly once')
    result = []
    for item in index:
        pid = item['patient_id']; spec = specs[pid]
        original = PatientObservationV2.model_validate(read(dataset/item['observation_ref']))
        # Re-project with actual host grants (none for conditional measurements).
        row = {'patient_id':pid, 'time_s':original.simulation_time_s,
               'values':{'vitals.'+k:v.value for k,v in original.vitals},
               'sample_times':{'vitals.'+k:v.observed_at_s for k,v in original.vitals}}
        observation = project(row, Access()).model_dump()
        injury = {k:spec['injury'][k] for k in ('injury_type','side','compartment') if k in spec['injury']}
        choices = []
        for p in plans:
            if p['plan_id'] not in item['plan_ids']:
                continue
            p = copy.deepcopy(p)
            for action in p['actions']:
                if action['target']['patient_id'] != pid:
                    raise ValueError('Cross-patient plan')
                kind = action['action_type']
                # Target semantics from shared mapping, never inherited injury anatomy.
                target_kind = target_rules[kind]['target_kind']
                action['injury_association'] = injury
                action['target'] = {'patient_id':pid}
                if target_kind in ('side','compartment'):
                    action['target'][target_kind] = injury[target_kind]
            choices.append(p)
        result.append({'patient_id':pid,'location':spec['location_id'],'arrival_time_min':spec['arrival_time_min'],
                       'pulse_sample_time_s':observation['simulation_time_s'], 'observation':observation,
                       'known_injury_context':injury, 'candidate_plans':choices})
    return result

def requirement(mapping, action, *, access_mode='new', mode='start'):
    """Same configuration supplies both Agent tasks and deterministic checks."""
    r = copy.deepcopy(mapping['actions'][action['action_type']])
    r['action_type'] = action['action_type']
    r['depends_on'] = list(action['depends_on'])
    r['target'] = copy.deepcopy(action['target'])
    access = r.get('access')
    r['access_phase_min'] = 0
    if access:
        if access_mode == 'new':
            r['consumables'].update(access['new_consumables'])
        if access['separate_phase']:
            r['access_phase_min'] = access['new_duration_min'] if access_mode=='new' else 0
            r['duration_min'] += r['access_phase_min']
        else:
            r['duration_min'] = access['new_duration_min'] if access_mode=='new' else access['existing_duration_min']
    if mode == 'continue':
        # Undefined handoff is exposed, not silently assigned an invented duration/cost.
        r['duration_min'] = r.get('continuation_duration_min')
        r['consumables'] = {}
        r['access_phase_min'] = 0
        r['staff_roles'] = r.get('continuation_staff_roles', r['staff_roles'])
    return r

def build_input(resources, mapping, cases, *, horizon_min=120.0, observation_time_min=60.0):
    if type(horizon_min) not in (int,float) or not math.isfinite(horizon_min) or horizon_min <= 0:
        raise ValueError('finite positive demonstration horizon required')
    if type(observation_time_min) not in (int,float) or not math.isfinite(observation_time_min) or not 0 <= observation_time_min <= horizon_min:
        raise ValueError('observation time must be finite and within planning horizon')
    patients = copy.deepcopy(cases)
    for p in patients:
        for plan in p['candidate_plans']:
            for a in plan['actions']:
                a['resource_requirements'] = requirement(mapping,a)
    return {'version':'301.resource_schedule.input.v1','time_unit':'scheduler_minutes',
            'horizon_min':float(horizon_min),'observation_time_min':float(observation_time_min),'purpose':'resource scheduling demonstration; eligibility not confirmed',
            'patients':patients,'resources':copy.deepcopy(resources), 'action_mapping':copy.deepcopy(mapping),
            'output_json_schema':Schedule.model_json_schema(),
            'constraints':['Return operations/transports/care with exact IDs from this input.',
                'Do not invent requirements, doses, grants or eligibility. All proposed plans require host validation.',
                'Ongoing support has unknown release: reserve throughout the planning horizon; the record ends only for accounting and support may continue beyond it. Observation time is not a task deadline.',
                'Observation clocks are Pulse time. All schedule times are scheduler minutes.']}

def make_tasks(context, selections):
    """Create unassigned resource task requests without confirming eligibility."""
    tasks = []
    for pid, plan_id in selections.items():
        patient = next(p for p in context['patients'] if p['patient_id'] == pid)
        plan = next(p for p in patient['candidate_plans'] if p['plan_id'] == plan_id)
        for action in plan['actions']:
            tasks.append({'patient_id':pid, 'plan_id':plan_id, 'action_id':action['action_id'],
                          'earliest_start_min':patient['arrival_time_min'],
                          'eligibility_status':action['eligibility_status'],
                          'requirements':requirement(context['action_mapping'], action),
                          'assignment_status':'unassigned'})
    return tasks

async def request_agent_schedule(provider, dispatch_input, *, feedback=None,
                                 previous_response=None, timeout_s=180, audit_dir=None):
    """One actual model request, followed by host validation. No implicit retries."""
    from openai import AsyncOpenAI
    from .validation import validate_schedule
    config = provider._config
    prompt = (PROJECT_ROOT/'src/core301/dispatch/prompts/resource_schedule.md').read_text()
    messages = [{'role':'system','content':prompt},
                {'role':'user','content':json.dumps(dispatch_input,ensure_ascii=False,allow_nan=False)}]
    if previous_response is not None:
        messages.append({'role':'assistant','content':previous_response})
    if feedback is not None:
        messages.append({'role':'user','content':json.dumps({'validator_feedback':feedback},ensure_ascii=False,allow_nan=False)})
    if audit_dir is not None:
        audit_dir = Path(audit_dir)
        audit_dir.mkdir(parents=True,exist_ok=True)
        (audit_dir/'request_messages.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2)+'\n')
    async with AsyncOpenAI(base_url=config.base_url, api_key=config.api_key, max_retries=0, timeout=timeout_s) as client:
        response = await client.chat.completions.create(model=config.model, messages=messages)
    content = response.choices[0].message.content if response.choices else None
    raw = content if isinstance(content,str) else ''
    usage = getattr(response,'usage',None)
    meta = {'requested_model':config.model,'returned_model':getattr(response,'model',None),
            'finish_reason':getattr(response.choices[0],'finish_reason',None) if response.choices else None,
            'usage':usage.model_dump() if usage is not None else None}
    if audit_dir is not None:
        (audit_dir/'response.txt').write_text(raw)
        (audit_dir/'response_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    try:
        if not raw.strip():raise ValueError('Empty response')
        candidate = json.loads(raw,parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (ValueError,TypeError):
        return {'schedule':None,'raw_response':raw,'metadata':meta,
                'validation':{'known_constraints_passed':False,'fully_verified':False,
                  'conflicts':[{'code':'MODEL_JSON_INVALID','detail':'Expected a nonempty strict JSON schedule; see response.txt'}],
                  'unchecked':[],'projected_occupancy':[],'projected_inventory_changes':[]}}
    validation = validate_schedule(dispatch_input,candidate)
    if not validation['conflicts']:
        candidate = Schedule.model_validate(candidate).model_dump()
        extra = []
        if not candidate['demonstration_only']:
            extra.append({'code':'DEMONSTRATION_FLAG_REQUIRED','detail':'This connection cannot authorize execution'})
        if extra:
            validation.update(known_constraints_passed=False,fully_verified=False,status='conflicts',
                              effects_status='rejected',projected_occupancy=[],projected_inventory_changes=[])
            validation['conflicts'].extend(extra)
    return {'schedule':candidate,'validation':validation,'raw_response':raw,'metadata':meta}
