"""Host-only injury-to-wound projection; never pass injury specs to the rules."""

LIMBS = {'RightLeg': 'right_leg', 'LeftLeg': 'left_leg',
         'RightArm': 'right_arm', 'LeftArm': 'left_arm'}
SIDES = {'Left': 'left_chest', 'Right': 'right_chest'}
GRADES = {0.2: 'mild', 0.4: 'moderate', 0.6: 'moderate', 0.8: 'severe', 1.0: 'severe'}
NO_WOUND = frozenset(('dehydration', 'carbon_monoxide_exposure', 'environmental_hypoxia',
                      'respiratory_muscle_impairment', 'impaired_alveolar_exchange'))


def describe_wounds(injury: dict) -> list[dict]:
    """Generate the single wound description specified for each V1 injury."""
    kind = injury['injury_type']
    wound = {'wound_type': 'none', 'body_region': 'none', 'grade': None, 'visibility': 'none'}
    if kind == 'external_hemorrhage':
        compartment = injury.get('compartment')
        if compartment not in LIMBS:
            raise ValueError(f'Unsupported external hemorrhage compartment: {compartment}')
        wound.update(wound_type='laceration', body_region=LIMBS[compartment], visibility='visible')
    elif kind in ('open_pneumothorax', 'closed_tension_pneumothorax', 'hemothorax'):
        side = injury.get('side')
        if side not in SIDES:
            raise ValueError(f'Unsupported chest side: {side}')
        wound.update(body_region=SIDES[side], visibility='hidden')
        if kind == 'open_pneumothorax':
            wound.update(wound_type='open_chest_wound', visibility='visible')
    elif kind == 'abdominal_internal_hemorrhage':
        wound.update(body_region='abdomen', visibility='hidden')
    elif kind not in NO_WOUND:
        raise ValueError(f'Unsupported injury type: {kind}')
    if wound['visibility'] == 'visible':
        severity = injury.get('severity')
        if type(severity) not in (int, float) or severity not in GRADES:
            raise ValueError(f'Visible wound severity is outside the V1 mapping: {severity}')
        wound['grade'] = GRADES[severity]
    return [wound]
