"""Bounded two-call real feedback provider, separate from priority/treatment prompts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from core301.agent.llm_config import load_llm_config
from core301.paths import PROJECT_ROOT

PROMPT=Path(__file__).with_name('prompts').joinpath('resource_feedback_decision_m3c2.md').read_text()
PROMPT_SHA=hashlib.sha256(PROMPT.encode()).hexdigest()

def append(path,value):
    with path.open('a') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')

class LLMTreatmentFeedbackProvider:
    max_calls=2
    max_completion_tokens=1000
    request_budget=24000 # UTF-8 input bytes + requested output tokens; conservative local request budget
    def __init__(self):
        self.config=load_llm_config(PROJECT_ROOT);self.calls=0;self.requested_budget=0
    def create_decision(self,payload,directory):
        if self.calls>=self.max_calls:raise RuntimeError('FEEDBACK_CALL_LIMIT')
        messages=[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(payload,ensure_ascii=False,allow_nan=False)}]
        budget=sum(len(m['content'].encode()) for m in messages)+self.max_completion_tokens
        if self.requested_budget+budget>self.request_budget:raise RuntimeError('FEEDBACK_REQUEST_BUDGET')
        self.calls+=1;self.requested_budget+=budget
        request={'model':self.config.model,'max_tokens':self.max_completion_tokens,'messages':messages}
        metadata={'call_index':self.calls,'decision_id':payload['feedback']['decision_id']}
        append(directory/'llm_requests.jsonl',{**metadata,'prompt_version':'m3c2.1','prompt_sha256':PROMPT_SHA,
            'requested_at':datetime.now(timezone.utc).isoformat(),'max_retries':0,'timeout_s':60,
            'request_budget_units':budget,'cumulative_request_budget_units':self.requested_budget,'parameters':request})
        try:
            with OpenAI(api_key=self.config.api_key,base_url=self.config.base_url,max_retries=0,timeout=60) as client:
                response=client.chat.completions.create(**request)
            append(directory/'llm_responses.jsonl',{**metadata,'response':response.model_dump(mode='json'),'cost':None})
            content=response.choices[0].message.content if response.choices else None
            if not isinstance(content,str) or not content.strip():raise ValueError('Empty model response')
            return content
        except Exception as exc:
            append(directory/'llm_errors.jsonl',{**metadata,'type':type(exc).__name__,'status_code':getattr(exc,'status_code',None),'retry_attempted':False})
            raise RuntimeError('FEEDBACK_LLM_FAILED:'+type(exc).__name__) from None
