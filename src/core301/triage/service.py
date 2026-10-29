"""Host orchestration and model-copy projection, separate from the triage rules."""
import copy

from .rules import triage
from .wounds import describe_wounds


def observed_vitals(observation: dict) -> tuple[float, float]:
    values = []
    for name in ('heart_rate', 'respiration_rate'):
        measurement = observation.get('vitals', {}).get(name)
        if not isinstance(measurement, dict) or measurement.get('status') != 'available':
            raise ValueError(f'{name} is not available in the observation snapshot')
        values.append(measurement.get('value'))
    return tuple(values)


def triage_cases(cases: list[dict], patient_specs: list[dict]) -> dict:
    """Project host specs first, then pass only wounds and observed HR/RR to triage."""
    specs = {s['patient_id']: s for s in patient_specs}
    if len(specs) != len(patient_specs) or len({c['patient_id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate patient ID')
    patients = []
    summary = dict.fromkeys(('red', 'yellow', 'green', 'black'), 0)
    for case in cases:
        pid = case['patient_id']
        wounds = describe_wounds(specs[pid]['injury'])
        HR, RR = observed_vitals(case['observation'])
        result = {'patient_id': pid, **triage(wounds, HR, RR)}
        patients.append(result)
        summary[result['tag']] += 1
    return {'patients': patients, 'summary': summary}


def with_triage_tags(context: dict, result: dict) -> dict:
    """L2 model input only: retain validator context and expose just the tags."""
    tags = {p['patient_id']: p['tag'] for p in result['patients']}
    model_input = copy.deepcopy(context)
    for patient in model_input['patients']:
        del patient['observation']
        patient['triage_tag'] = tags[patient['patient_id']]
    return model_input
