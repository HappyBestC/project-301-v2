"""Check actual saved demo output, including every resource conservation equation."""
from pathlib import Path
import os
import json
R=Path(__file__).resolve().parents[1]/os.environ.get('CORE301_VALIDATION_DIR', 'validation')
def rows(n):return [json.loads(x) for x in (R/n).read_text().splitlines()]
a=rows('shared_resources.demo.jsonl');b=rows('shared_demo.jsonl');c=rows('complete_demo.jsonl')
aa={r['step']:r for r in a};bb={r['step']:r for r in b}
assert aa['A-reserve']['result']['outcome']=='SATISFIED'
assert aa['B-conflict']['result']['outcome']=='UNSATISFIED'
assert aa['B-reserve-after-release']['result']['outcome']=='SATISFIED'
assert bb['A-dispatch-reserved']['result']['allocated']
assert not bb['B-dispatch-conflict']['result']['allocated']
assert bb['B-dispatch-retry-reserved']['result']['allocated']
assert [r['result']['allocated'] for r in c]==[True,False]
for r in c:
 assert r['input_plan']==r['agent_received_plan']
 assert [x['action_type'] for x in r['input_plan']['actions']]==['occlusive_dressing','control_hemothorax_bleeding','chest_tube']
assert [(r['before']['state_version'],r['after']['state_version']) for r in c]==[(0,1),(1,1)]
snapshots=[r for r in a]+[r['snapshot'] for r in b]+[r[k] for r in c for k in ('before','after')]
n=0
for s in snapshots:
 for x in s['resources'].values():
  assert x['initial_total']+x['received_qty']-x['consumed_qty']-x['lost_qty']==x['total_qty']
  assert x['available_qty']+x['reserved_qty']+x['in_use_qty']+x['unavailable_qty']==x['total_qty']
  n+=1
print(json.dumps({'demo_records':[len(a),len(b),len(c)],'resource_conservation_checks':n,'complete_plan_lossless':True,'competition_and_release_retry':True,'complete_versions':[[0,1],[1,1]]},indent=2))
