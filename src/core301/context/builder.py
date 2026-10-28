from core301.contracts.context import AgentCaseContext
from .known_injury_projector import project_known_injuries


class ContextBuildError(ValueError):
    pass


class AgentCaseContextBuilder:
    def build(self, casualty, observation, resources):
        try:
            return AgentCaseContext(patient_id=casualty.patient_id,
                                    known_injuries=project_known_injuries(casualty),
                                    patient_observation=observation, available_resources=resources)
        except ValueError as exc:
            raise ContextBuildError(str(exc)) from exc
