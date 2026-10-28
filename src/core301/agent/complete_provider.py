"""One bounded real request, separate from the compatible V1 provider."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from core301.agent.llm_config import load_llm_config
from core301.paths import PROJECT_ROOT

PROMPT = Path(__file__).with_name('prompts').joinpath('treatment_decision_m3a.md').read_text()
PROMPT_SHA = hashlib.sha256(PROMPT.encode()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


class LLMCompleteTreatmentProvider:
    provider_name = 'LLMCompleteTreatmentProvider'

    def __init__(self):
        self.config = load_llm_config(PROJECT_ROOT)
        self.called = False

    def create_decision(self, payload, directory):
        if self.called:
            raise RuntimeError('One decision call per provider; no retry/fallback')
        self.called = True
        request = dict(model=self.config.model, max_tokens=1200, messages=[
            {'role':'system','content':PROMPT},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False,allow_nan=False)}])
        write(directory/'llm_request.json',dict(provider=self.provider_name,prompt_sha256=PROMPT_SHA,
            requested_at=datetime.now(timezone.utc).isoformat(),max_retries=0,timeout_s=60,parameters=request))
        try:
            with OpenAI(api_key=self.config.api_key,base_url=self.config.base_url,max_retries=0,timeout=60) as client:
                response=client.chat.completions.create(**request)
            # Raw server response and genuine metadata, never fabricated cost/usage.
            write(directory/'llm_response.json',dict(received_at=datetime.now(timezone.utc).isoformat(),
                response=response.model_dump(mode='json'),cost=None,cost_status='not_provided'))
            content=response.choices[0].message.content if response.choices else None
            if not isinstance(content,str) or not content.strip():
                raise ValueError('Empty model response')
            return content
        except Exception as exc:
            # Exception strings can contain headers/URLs supplied by gateways.
            write(directory/'llm_error.json',{'type':type(exc).__name__,
                'status_code':getattr(exc,'status_code',None),'retry_attempted':False})
            raise RuntimeError('LLM_CALL_FAILED:'+type(exc).__name__) from None
