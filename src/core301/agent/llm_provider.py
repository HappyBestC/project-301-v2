"""One plain Chat Completions request; Frozen TreatmentPlan remains authoritative."""
import json
from pathlib import Path

from openai import OpenAI
from core301.agent.llm_config import LLMConfigurationError, load_llm_config

from core301.contracts.context import AgentCaseContext
from core301.contracts.treatment import TreatmentPlan
from core301.paths import PROJECT_ROOT


SYSTEM_PROMPT = (Path(__file__).resolve().parent / "prompts" / "treatment_decision.md").read_text(
    encoding="utf-8"
)


class LLMEmptyResponseError(RuntimeError):
    pass


class LLMTreatmentProvider:
    def __init__(self):
        config = load_llm_config(PROJECT_ROOT)
        self._base_url = config.base_url
        self._api_key = config.api_key
        self._model = config.model

    def create_plan(self, context: AgentCaseContext) -> TreatmentPlan:
        context = AgentCaseContext.model_validate(context)
        payload = {
            "patient_id": context.patient_id,
            "known_injuries": [injury.model_dump() for injury in context.known_injuries],
            "patient_observation": context.patient_observation.model_dump(),
        }
        # Disable SDK retries too; expose the first failure without fallback.
        with OpenAI(api_key=self._api_key, base_url=self._base_url,
                    max_retries=0, timeout=60.0) as client:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)},
                ],
            )
        content = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise LLMEmptyResponseError("LLM returned no text content")
        # Do not strip fences, repair JSON, fill fields, or replace invalid actions.
        plan = TreatmentPlan.model_validate(json.loads(content))
        if plan.patient_id != context.patient_id:
            raise ValueError("LLM plan patient_id does not match context")
        return plan
