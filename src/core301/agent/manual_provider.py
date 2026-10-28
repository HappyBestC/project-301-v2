from core301.contracts.context import AgentCaseContext
from core301.contracts.treatment import TreatmentPlan


class ManualTreatmentProvider:
    def __init__(self, plan):
        self.plan = TreatmentPlan.model_validate(plan)

    def create_plan(self, context):
        context = AgentCaseContext.model_validate(context)
        plan = TreatmentPlan.model_validate(self.plan)
        if plan.patient_id != context.patient_id:
            raise ValueError("plan patient_id does not match context")
        return plan
