"""Phase-2 unsuccessful protocol admission must not bypass existing gates."""
import copy
import pytest
from core301.contracts.v2.injury import CasualtyInput
from core301.contracts.v2.treatment import TreatmentPlan
from core301.pulse.v2.protocol_book import OPEN_INJURIES, ALLOWED_ACTIONS, SPECIALTY_DECISIONS
from core301.pulse.v2.treatment_adapter import TreatmentAdapter
from core301.runtime.v2.case_runtime import CaseRuntime
from core301.runtime.v2.errors import V2Error
from core301.runtime.v2.injury_registry import InjuryRegistry
from core301.runtime.v2.resources import explicit_test_resources
from tests.v2.test_contracts import casualty
from tests.v2.test_runtime import SessionFaultFixture

CASES=[('hemothorax','control_hemothorax_bleeding'),('hemothorax','chest_tube'),
       ('bronchoconstriction','inhaled_albuterol'),('acute_lung_impairment_ards','supplemental_oxygen')]


def plan(kind,action):
 body={'action_type':action}
 if kind=='hemothorax':body['side']='Left'
 return TreatmentPlan.model_validate({'patient_id':'P','actions':[body]})


@pytest.mark.parametrize('kind,action',CASES)
@pytest.mark.parametrize('with_resources',[False,True])
def test_independent_native_success_never_opens_runtime(tmp_path,kind,action,with_resources):
 fixture=explicit_test_resources('r','P') if with_resources else None
 before=copy.deepcopy(fixture.audit()) if fixture else None
 session=SessionFaultFixture()
 rt=CaseRuntime('P',tmp_path,run_id='r',mode='research',resources=fixture,session=session)
 data=casualty(kind,.8 if kind=='hemothorax' else .4)
 assert plan(kind,action).actions
 with pytest.raises(V2Error) as error:rt.prepare(data)
 assert error.value.code=='INJURY_NOT_OPEN'
 assert SPECIALTY_DECISIONS[kind][0] in str(error.value)
 assert not session.action_results and session.time==0
 if fixture:assert fixture.audit()==before
 with pytest.raises(V2Error) as treatment:rt.execute_plan(plan(kind,action),request_id='blocked',context_ref='unissued')
 assert treatment.value.code=='NOT_PREPARED'


@pytest.mark.parametrize('kind,action',CASES)
def test_direct_adapter_cannot_launder_unapproved_profile(kind,action):
 registry=InjuryRegistry('P');registry.register(casualty(kind,.8 if kind=='hemothorax' else .4))
 with pytest.raises(V2Error) as err:TreatmentAdapter().convert(plan(kind,action).actions[0],registry.sources()[0],'albuterol.single90.bronch04.phase2.1')
 assert err.value.code=='ACTION_NOT_OPEN'


def test_phase1_allowlist_remains_exact():
 assert set(OPEN_INJURIES)=={'external_hemorrhage','abdominal_internal_hemorrhage','open_pneumothorax','closed_tension_pneumothorax','respiratory_muscle_impairment','impaired_alveolar_exchange','dehydration'}
 assert len(set().union(*ALLOWED_ACTIONS.values()))==9
 assert all(kind not in OPEN_INJURIES for kind in SPECIALTY_DECISIONS)
