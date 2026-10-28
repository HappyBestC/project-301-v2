import asyncio
import copy
import json

import pytest

from core301.agent_chain.treatment import (FakeTreatmentProvider, admit, build_treatment_input,
                                          decode, template_decisions)


def decision(pid='P01', actions=None):
    return {'schema_version': '301.treatment.candidates.v1', 'patient_id': pid,
            'decision_type': 'propose_candidates', 'candidate_plans': [
                {'actions': actions or ['control_external_bleeding', 'fluid_resuscitation'], 'rationale': 'test'}],
            'reasoning_summary': 'test', 'refusal_reason': None}


@pytest.mark.parametrize('change', [
    lambda d: d['candidate_plans'][0].update(actions=['invented_action']),
    lambda d: d['candidate_plans'][0].update(actions=['fluid_resuscitation', 'control_external_bleeding']),
    lambda d: d['candidate_plans'][0].update(actions=['control_external_bleeding'] * 2),
    lambda d: d['candidate_plans'].append(copy.deepcopy(d['candidate_plans'][0])),
    lambda d: d.update(patient_id='P02'),
    lambda d: d.update(decision_type='no_treatment_needed', candidate_plans=[], refusal_reason=None),
    lambda d: d.update(decision_type='no_treatment_needed', candidate_plans=[], refusal_reason='  '),
    lambda d: d.update(candidate_plans=[]),
    lambda d: d['candidate_plans'][0].update(actions=[]),
    lambda d: d['candidate_plans'][0].update(actions='control_external_bleeding'),
    lambda d: d.update(patient_id=1),
    lambda d: d.update(extra=True),
    lambda d: d['candidate_plans'][0].update(extra=True),
    lambda d: d.update(candidate_plans=d['candidate_plans'] * 3),
])
def test_admission_rejects_invalid_decisions(chain_data, change):
    cases, mapping, _, _ = chain_data
    raw = decision()
    change(raw)
    with pytest.raises(ValueError):
        admit(json.dumps(raw), build_treatment_input(cases[0], mapping), mapping,
              plan_status='agent_proposed_not_executed')


@pytest.mark.parametrize('raw', [
    '{"patient_id":"P01","patient_id":"P02"}',
    '{"candidate_plans":[{"actions":[],"actions":[]}]}',
    '{"patient_id":NaN}', '{"patient_id":Infinity}', '```json\n{}\n```', '', '[]',
])
def test_strict_json_rejects_duplicates_nonfinite_and_nonobjects(raw):
    with pytest.raises(ValueError):
        decode(raw)


def test_mechanical_ventilation_requires_earlier_intubation(chain_data):
    cases, mapping, _, _ = chain_data
    case = next(c for c in cases if c['patient_id'] == 'P03')
    with pytest.raises(ValueError, match='Predecessor'):
        admit(json.dumps(decision('P03', ['mechanical_ventilation'])), build_treatment_input(case, mapping),
              mapping, plan_status='agent_proposed_not_executed')


def test_no_treatment_produces_single_empty_host_plan(chain_data):
    cases, mapping, _, _ = chain_data
    raw = decision()
    raw.update(decision_type='no_treatment_needed', candidate_plans=[], refusal_reason='No treatment needed')
    _, plans = admit(json.dumps(raw), build_treatment_input(cases[0], mapping), mapping,
                     plan_status='agent_proposed_not_executed')
    assert plans == [{'plan_id': 'P01-plan-1', 'injury_type': 'external_hemorrhage',
                      'status': 'agent_proposed_not_executed', 'actions': []}]


def test_input_contains_only_approved_current_observations(chain_data):
    cases, mapping, _, _ = chain_data
    case = cases[0]
    case['known_injury_context']['severity'] = 0.9
    case['observation']['circulation'] = {'future': 'hidden'}
    case['observation']['vitals']['heart_rate']['backend_note'] = 'hidden'
    case['raw'] = {'secret': True}
    payload = build_treatment_input(case, mapping)
    assert set(payload) == {'patient_id', 'location', 'arrival_time_min', 'known_injury_context',
                            'observation', 'allowed_actions', 'action_descriptions'}
    assert len(payload['observation']['vitals']) == 5
    assert payload['observation']['vitals']['heart_rate']['unit'] == '1/min'
    assert payload['observation']['vitals']['pulse_oximetry']['unit'] == 'fraction'
    text = json.dumps(payload)
    for forbidden in ('severity', 'hidden', 'candidate_plans', 'personnel', 'inventory', 'vehicles', 'raw'):
        assert forbidden not in text
    for description in payload['action_descriptions'].values():
        assert set(description) == {'allowed_start', 'predecessor_actions', 'injury_predecessors'}


def test_llm_plan_expansion_uses_only_host_ids_targets_and_references(chain_data):
    cases, mapping, _, _ = chain_data
    case = cases[0]
    _, plans = admit(template_decisions()['P01'], build_treatment_input(case, mapping), mapping,
                     plan_status='agent_proposed_not_executed')
    expected = copy.deepcopy(case['candidate_plans'])
    for plan in expected:
        plan['status'] = 'agent_proposed_not_executed'
    assert plans == expected
    assert plans[0]['actions'][1]['target'] == {'patient_id': 'P01'}


def test_fake_returns_invalid_json_unchanged(tmp_path):
    provider = FakeTreatmentProvider({'P01': '{broken'})
    assert asyncio.run(provider.propose({'patient_id': 'P01'}, audit_dir=tmp_path)) == '{broken'
