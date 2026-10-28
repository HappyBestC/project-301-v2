"""User-triggered live run, exact bundled input, existing runner, max three requests."""
import sys,argparse,asyncio,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from core301.dispatch.minimal.agent_run import run_agent
from core301.dispatch.providers import LLMDispatchProvider
p=argparse.ArgumentParser(description='Live API call; does not execute treatment')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
output=a.output.resolve()
if output.exists():p.error('Output must be a new directory; existing evidence is protected')
context=json.loads((ROOT/'runs/medical_resources_deepseek_001/dispatch_input.json').read_text())
provider=LLMDispatchProvider()
asyncio.run(run_agent(provider,context,output,max_attempts=3,timeout_s=180))
