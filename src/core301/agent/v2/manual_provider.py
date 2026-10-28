from core301.contracts.v2.context import AgentCaseContext
from core301.contracts.v2.treatment import TreatmentPlan
from core301.runtime.v2.errors import V2Error


class ManualTreatmentProvider:
    def __init__(self, plan):
        self.plan=TreatmentPlan.model_validate(plan)

    def create_plan(self, context: AgentCaseContext):
        if not isinstance(context,AgentCaseContext) or self.plan.patient_id!=context.patient_id:
            raise V2Error("PATIENT_MISMATCH", "V2 provider requires matching authorized public context")
        # Own copy; backend transport/registry never enters this method.
        return TreatmentPlan.model_validate(self.plan.model_dump())
