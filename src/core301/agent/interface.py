from typing import Protocol
from core301.contracts.context import AgentCaseContext
from core301.contracts.treatment import TreatmentPlan


class TreatmentProvider(Protocol):
    def create_plan(self, context: AgentCaseContext) -> TreatmentPlan: ...
