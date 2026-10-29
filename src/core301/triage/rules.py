"""Ordered BCD Sieve rules from TRIAGE_V1_DEV_SPEC.md, using observables only."""
import copy
import math


def _finite(name, value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be an available finite number')


def is_ambulatory(wounds: list[dict], HR: float, RR: float) -> bool:
    _finite('HR', HR)
    _finite('RR', RR)
    leg_wound = any(w['body_region'] in ('left_leg', 'right_leg')
                    and w['grade'] in ('moderate', 'severe') for w in wounds)
    return not (leg_wound or HR > 100 or RR < 12 or RR > 23)


def triage(wounds: list[dict], HR: float, RR: float, GCS: float = 15) -> dict:
    """Classify observables without injury specs, severity, files or model calls."""
    ambulatory = is_ambulatory(wounds, HR, RR)
    _finite('GCS', GCS)
    if any(w['wound_type'] == 'laceration' and w['visibility'] == 'visible'
           and w['grade'] in ('moderate', 'severe') for w in wounds):
        tag, code, reason = 'red', 'CATASTROPHIC_HEMORRHAGE', '可见中度或重度裂伤出血'
    elif ambulatory:
        tag, code, reason = 'green', 'AMBULATORY', '能行走'
    elif RR == 0:
        tag, code, reason = 'black', 'NOT_BREATHING', '无呼吸（RR = 0）'
    elif GCS <= 8:
        tag, code, reason = 'red', 'LOW_GCS', f'意识水平低（GCS = {GCS} <= 8）'
    elif RR < 12 or RR > 23:
        comparison = f'{RR} < 12' if RR < 12 else f'{RR} > 23'
        tag, code, reason = 'red', 'ABNORMAL_RESPIRATION', f'呼吸频率异常（{comparison}）'
    elif HR > 100:
        tag, code, reason = 'red', 'TACHYCARDIA', f'心率过快（{HR} > 100）'
    else:
        tag, code, reason = 'yellow', 'DEFAULT_DELAYED', '不能行走，未命中立即处置或无呼吸条件'
    return {'tag': tag, 'reason_code': code, 'reason': reason, 'ambulatory': ambulatory,
            'inputs': {'wounds': copy.deepcopy(wounds), 'HR': HR, 'RR': RR, 'GCS': GCS}}
