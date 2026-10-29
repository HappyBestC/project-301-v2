import copy
import inspect
import json

import pytest

from core301.agent_chain.scenarios import scenario_paths
from core301.dispatch.minimal import api
from core301.triage import cli, rules, service
from core301.triage.wounds import describe_wounds


def wound(wound_type='laceration', region='right_leg', grade='moderate', visibility='visible'):
    return dict(wound_type=wound_type, body_region=region, grade=grade, visibility=visibility)


@pytest.mark.parametrize('injury,expected', [
    ({'injury_type': 'external_hemorrhage', 'compartment': 'RightLeg', 'severity': 0.2}, wound(grade='mild')),
    ({'injury_type': 'open_pneumothorax', 'side': 'Left', 'severity': 0.6}, wound('open_chest_wound', 'left_chest')),
    ({'injury_type': 'closed_tension_pneumothorax', 'side': 'Left', 'severity': 0.8}, wound('none', 'left_chest', None, 'hidden')),
    ({'injury_type': 'hemothorax', 'side': 'Right', 'severity': 1.0}, wound('none', 'right_chest', None, 'hidden')),
    ({'injury_type': 'abdominal_internal_hemorrhage', 'compartment': 'Spleen', 'severity': 0.8}, wound('none', 'abdomen', None, 'hidden')),
    *[({'injury_type': kind}, wound('none', 'none', None, 'none')) for kind in (
        'dehydration', 'carbon_monoxide_exposure', 'environmental_hypoxia',
        'respiratory_muscle_impairment', 'impaired_alveolar_exchange')],
])
def test_each_injury_description(injury, expected):
    original = copy.deepcopy(injury)
    assert describe_wounds(injury) == [expected]
    assert injury == original


@pytest.mark.parametrize('compartment,region', [('LeftLeg', 'left_leg'), ('RightLeg', 'right_leg'),
                                              ('LeftArm', 'left_arm'), ('RightArm', 'right_arm')])
def test_external_hemorrhage_limbs(compartment, region):
    assert describe_wounds(dict(injury_type='external_hemorrhage', compartment=compartment, severity=0.4)) == [
        wound(region=region)]


@pytest.mark.parametrize('kind', ['open_pneumothorax', 'closed_tension_pneumothorax', 'hemothorax'])
@pytest.mark.parametrize('side,region', [('Left', 'left_chest'), ('Right', 'right_chest')])
def test_chest_sides(kind, side, region):
    assert describe_wounds(dict(injury_type=kind, side=side, severity=0.4))[0]['body_region'] == region


@pytest.mark.parametrize('severity,grade', [(0.2, 'mild'), (0.4, 'moderate'), (0.6, 'moderate'),
                                          (0.8, 'severe'), (1.0, 'severe')])
@pytest.mark.parametrize('kind,anatomy', [('external_hemorrhage', {'compartment': 'RightArm'}),
                                       ('open_pneumothorax', {'side': 'Right'})])
def test_visible_severity_bins(kind, anatomy, severity, grade):
    assert describe_wounds(dict(injury_type=kind, severity=severity, **anatomy))[0]['grade'] == grade


@pytest.mark.parametrize('kind,anatomy', [
    ('closed_tension_pneumothorax', {'side': 'Left'}), ('hemothorax', {'side': 'Right'}),
    ('abdominal_internal_hemorrhage', {'compartment': 'Spleen'}),
    *[(kind, {}) for kind in ('dehydration', 'carbon_monoxide_exposure', 'environmental_hypoxia',
                              'respiratory_muscle_impairment', 'impaired_alveolar_exchange')],
])
def test_nonvisible_description_does_not_read_severity(kind, anatomy):
    class NoSeverity(dict):
        def get(self, key, *args):
            assert key != 'severity'
            return super().get(key, *args)

        def __getitem__(self, key):
            assert key != 'severity'
            return super().__getitem__(key)

    assert describe_wounds(NoSeverity(injury_type=kind, **anatomy))[0]['grade'] is None


@pytest.mark.parametrize('compartment', ['Spleen', 'Aorta', None])
def test_unsupported_hemorrhage_compartment_is_an_error(compartment):
    with pytest.raises(ValueError, match='compartment'):
        describe_wounds(dict(injury_type='external_hemorrhage', compartment=compartment, severity=0.4))


@pytest.mark.parametrize('severity', [None, True, 0.3])
def test_visible_grade_does_not_guess_an_unlisted_mapping(severity):
    with pytest.raises(ValueError, match='V1 mapping'):
        describe_wounds(dict(injury_type='external_hemorrhage', compartment='RightLeg', severity=severity))


def test_triage_signature_is_observables_only():
    parameters = inspect.signature(rules.triage).parameters
    assert list(parameters) == ['wounds', 'HR', 'RR', 'GCS']
    assert parameters['GCS'].default == 15
    for keyword in ('severity', 'injury', 'patient_specs', 'patient_id'):
        with pytest.raises(TypeError):
            rules.triage([], 80, 16, **{keyword: {}})


@pytest.mark.parametrize('wounds,HR,RR,GCS,tag,code', [
    ([wound()], 120, 0, 3, 'red', 'CATASTROPHIC_HEMORRHAGE'),
    ([], 80, 16, 3, 'green', 'AMBULATORY'),
    ([], 120, 0, 3, 'black', 'NOT_BREATHING'),
    ([], 120, 11, 8, 'red', 'LOW_GCS'),
    ([], 120, 11, 15, 'red', 'ABNORMAL_RESPIRATION'),
    ([], 101, 16, 15, 'red', 'TACHYCARDIA'),
    # Synthetic observable leg wound exercises the final branch independently
    # of the V1 backend's limited injury catalogue; it is not a new mapping.
    ([wound(wound_type='none')], 80, 16, 15, 'yellow', 'DEFAULT_DELAYED'),
])
def test_all_seven_steps_in_order(wounds, HR, RR, GCS, tag, code):
    result = rules.triage(wounds, HR, RR, GCS)
    assert (result['tag'], result['reason_code']) == (tag, code)
    assert result['reason']
    assert result['inputs'] == {'wounds': wounds, 'HR': HR, 'RR': RR, 'GCS': GCS}


@pytest.mark.parametrize('HR,RR,tag,code', [
    (100, 12, 'green', 'AMBULATORY'), (100, 23, 'green', 'AMBULATORY'),
    (100, 12.048, 'green', 'AMBULATORY'),
    (80, 11.99, 'red', 'ABNORMAL_RESPIRATION'), (80, 23.01, 'red', 'ABNORMAL_RESPIRATION'),
    (100.01, 16, 'red', 'TACHYCARDIA'),
])
def test_exact_thresholds_without_rounding(HR, RR, tag, code):
    result = rules.triage([], HR, RR)
    assert (result['tag'], result['reason_code']) == (tag, code)


@pytest.mark.parametrize('wounds,HR,RR,expected', [
    ([wound(grade='mild')], 80, 16, True),
    ([wound()], 80, 16, False),
    ([wound(region='left_leg', grade='severe')], 80, 16, False),
    ([wound(region='left_arm', grade='severe')], 80, 16, True),
    ([], 100.01, 16, False), ([], 80, 11.99, False), ([], 80, 23.01, False),
])
def test_ambulation(wounds, HR, RR, expected):
    assert rules.is_ambulatory(wounds, HR, RR) is expected


def test_hemorrhage_requires_visible_laceration_and_scans_whole_list():
    assert rules.triage([wound(region='left_arm', grade='severe')], 80, 16)['reason_code'] == 'CATASTROPHIC_HEMORRHAGE'
    for value in [wound(visibility='hidden'), wound(visibility='none'), wound(wound_type='open_chest_wound')]:
        assert rules.triage([value], 80, 16)['reason_code'] == 'DEFAULT_DELAYED'
    assert rules.triage([wound(grade='mild'), wound(region='right_arm')], 80, 16)['reason_code'] == 'CATASTROPHIC_HEMORRHAGE'


def test_input_and_result_are_independent():
    wounds = [wound()]
    original = copy.deepcopy(wounds)
    result = rules.triage(wounds, 80, 16)
    assert wounds == original
    result['inputs']['wounds'][0]['grade'] = 'mild'
    assert wounds == original


@pytest.mark.parametrize('field', ['heart_rate', 'respiration_rate'])
@pytest.mark.parametrize('status', ['unavailable', 'not_measured', None])
def test_unavailable_vitals_are_errors(field, status):
    observation = {'vitals': {name: dict(status='available', value=80 if name == 'heart_rate' else 16)
                             for name in ('heart_rate', 'respiration_rate')}}
    observation['vitals'][field]['status'] = status
    with pytest.raises(ValueError, match=field):
        service.observed_vitals(observation)


@pytest.mark.parametrize('observation', [{}, {'vitals': {}}, {'vitals': {'heart_rate': {'status': 'available', 'value': 80}}}])
def test_missing_vital_records_are_errors(observation):
    with pytest.raises(ValueError, match='not available'):
        service.observed_vitals(observation)


@pytest.mark.parametrize('field', ['HR', 'RR'])
@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), True])
def test_missing_or_nonnumeric_values_cannot_be_classified(field, value):
    inputs = dict(wounds=[wound()], HR=80, RR=16)
    inputs[field] = value
    with pytest.raises(ValueError, match=field):
        rules.triage(**inputs)


EXPECTED = {
    **{pid: ('red', 'CATASTROPHIC_HEMORRHAGE') for pid in ('P01', 'P09', 'P15')},
    **{pid: ('red', 'TACHYCARDIA') for pid in ('P05', 'P10', 'P11', 'P14')},
    **{pid: ('green', 'AMBULATORY') for pid in ('P02', 'P03', 'P04', 'P06', 'P07', 'P08', 'P12', 'P13', 'P16')},
}


def test_run_002_acceptance_and_host_input_isolation(monkeypatch):
    dataset = scenario_paths('run_002')['dataset_dir']
    cases, specs = api.load_cases(dataset), api.read(dataset / 'patient_specs.json')
    original = copy.deepcopy((cases, specs))
    calls = []

    def spy(wounds, HR, RR, GCS=15):
        calls.append((copy.deepcopy(wounds), HR, RR, GCS))
        return rules.triage(wounds, HR, RR, GCS)

    monkeypatch.setattr(service, 'triage', spy)
    result = service.triage_cases(cases, specs)
    assert {p['patient_id']: (p['tag'], p['reason_code']) for p in result['patients']} == EXPECTED, result
    assert result['summary'] == dict(red=7, yellow=0, green=9, black=0)
    assert (cases, specs) == original
    assert len(calls) == 16
    for case, patient, (wounds, HR, RR, GCS) in zip(cases, result['patients'], calls):
        assert patient['patient_id'] == case['patient_id']
        assert HR == case['observation']['vitals']['heart_rate']['value']
        assert RR == case['observation']['vitals']['respiration_rate']['value']
        assert GCS == 15
        assert all(set(w) == {'wound_type', 'body_region', 'grade', 'visibility'} for w in wounds)


def test_cli_uses_only_stored_snapshots(tmp_path, monkeypatch, capsys):
    import openai
    from core301.pulse.session import PulseSession

    def forbidden(*args, **kwargs):
        pytest.fail('Triage CLI must not call a model or initialize Pulse')

    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(openai, 'AsyncOpenAI', forbidden)
    monkeypatch.setattr(PulseSession, '_create_engine', forbidden)
    monkeypatch.chdir(tmp_path)
    assert cli.main(['--scenario', 'run_002']) == 0
    result = json.loads((tmp_path / 'triage.json').read_text())
    output = capsys.readouterr().out
    assert result['summary'] == dict(red=7, yellow=0, green=9, black=0)
    for patient in result['patients']:
        line = next(line for line in output.splitlines() if line.startswith(patient['patient_id'] + ' '))
        assert 'wounds=' in line and 'HR=' in line and 'RR=' in line
        assert patient['tag'] in line and patient['reason_code'] in line and patient['reason'] in line


def test_cli_missing_vital_fails_without_an_output(tmp_path, monkeypatch):
    dataset = scenario_paths('run_002')['dataset_dir']
    cases = api.load_cases(dataset)
    del cases[0]['observation']['vitals']['heart_rate']
    monkeypatch.setattr(api, 'load_cases', lambda path: cases)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='heart_rate'):
        cli.main(['--scenario', 'run_002'])
    assert not (tmp_path / 'triage.json').exists()
