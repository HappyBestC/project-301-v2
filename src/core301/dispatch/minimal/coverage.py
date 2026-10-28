"""Outcome accounting only; model explanations are not infeasibility proofs."""
import re
from collections import Counter

SUMMARY_KEYS = ('loaded_patients', 'accounted_patients', 'scheduled_patients', 'unscheduled_patients',
                'all_patients_accounted_for', 'all_patients_scheduled', 'scheduled_patient_ids',
                'unscheduled_patient_ids', 'unscheduled_reasons', 'outcome_status')

def accounting(context, schedule=None):
    patients={p['patient_id'] for p in context['patients']}
    results=schedule.patient_results if schedule else []
    counts=Counter(x.patient_id for x in results)
    accounted={pid for pid in patients if counts[pid]==1}
    scheduled={x.patient_id for x in results if x.patient_id in accounted and x.status=='scheduled'}
    unscheduled={x.patient_id for x in results if x.patient_id in accounted and x.status=='unscheduled'}
    complete=accounted==patients and set(counts)==patients
    return dict(loaded_patients=len(patients),accounted_patients=len(accounted),
                scheduled_patients=len(scheduled),unscheduled_patients=len(unscheduled),
                all_patients_accounted_for=complete,all_patients_scheduled=complete and scheduled==patients,
                scheduled_patient_ids=sorted(scheduled),unscheduled_patient_ids=sorted(unscheduled),
                unscheduled_reasons=[x.model_dump() for x in results if x.status=='unscheduled'],
                outcome_status='结果不完整' if not complete else '部分调度，原因已说明' if unscheduled else '全员排程通过已知约束')

def check_results(context, schedule, issue):
    patients={p['patient_id'] for p in context['patients']}
    counts=Counter(x.patient_id for x in schedule.patient_results)
    for pid in sorted(patients-set(counts)):
        issue('PATIENT_RESULT_MISSING',f'Missing outcome for {pid}',resource=pid)
    r=context['resources']
    ids=patients|set(r['nodes'])|set(r['vehicles'])
    ids|={a['id'] for key in ('personnel','equipment','spaces','service_capacities') for a in r.get(key,[])}
    ids|={f'{loc}:{kind}' for loc,stock in r['inventory'].items() for kind in stock}
    ids|={f"{a['location']}:{a['type']}" for key in ('equipment','spaces','service_capacities') for a in r.get(key,[])}
    ids|={f"{a['location']}:{cap}" for a in r['personnel'] for cap in a['capabilities']}
    # Only explicit ID syntax is checked, not a claim that free prose proves infeasibility.
    pattern=r'(?<![A-Za-z0-9_])(?:P\d+|(?:H\d+|V\d+|A|B)(?:[-:][A-Za-z0-9_-]+)?)(?![A-Za-z0-9_])'
    for result in schedule.patient_results:
        pid=result.patient_id
        if pid not in patients:issue('PATIENT_RESULT_UNKNOWN','Patient is outside input',result)
        if counts[pid]!=1:issue('PATIENT_RESULT_DUPLICATE','Exactly one outcome required',result)
        if result.status=='scheduled':
            if pid not in schedule.selections:issue('SCHEDULED_PLAN_MISSING','Scheduled outcome requires a selected complete plan',result)
        else:
            if pid in schedule.selections or any(t.patient_id==pid for t in schedule.operations+schedule.care+schedule.transports):
                issue('UNSCHEDULED_HAS_TASKS','Unscheduled patient cannot retain selections or tasks',result)
            text=re.sub(r'\s+','',result.reason).strip('。.!！')
            generic={'未安排','资源不足','无法安排','未找到可行安排','unscheduled','resourceshortage'}
            if not result.reason_code or len(text)<12 or text.lower() in generic:
                issue('UNSCHEDULED_REASON_REQUIRED','Supply a specific obstacle, not a generic label',result)
            if not result.considered_alternatives or any(not x.strip() for x in result.considered_alternatives):
                issue('ALTERNATIVES_REQUIRED','Explain considered alternatives and why not used',result)
            if result.reason_code=='resource_shortage' and not result.blocking_resources:
                issue('BLOCKING_RESOURCE_REQUIRED','Identify the local resource shortage',result)
            if result.reason_code=='missing_parameters':
                issue('UNSCHEDULED_PARAMETERS_UNCHECKED',result.reason,result,unknown=True)
        for ref in result.blocking_resources:
            if ref not in ids:issue('REASON_UNKNOWN_REFERENCE','Unknown blocking resource reference',result,ref)
        for ref in re.findall(pattern,' '.join([result.reason]+result.considered_alternatives)):
            if ref not in ids:issue('TEXT_REFERENCE_UNVERIFIED','Unrecognized ID in free text; nonblocking, meaning not verified',result,ref,unknown=True)
