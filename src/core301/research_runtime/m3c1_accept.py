"""Read-only aggregate admission: real priority experiment plus both native baselines."""
import argparse
import json
from pathlib import Path
from .m3c1_verify import verify

def accept(real,baseline_a,baseline_b):
    reports=[]; backend_hashes=[]
    for path,mode in [(real,'llm_priority'),(baseline_a,'fixed_A_first'),(baseline_b,'fixed_B_first')]:
        manifest=json.loads((Path(path)/'run_manifest.json').read_text())
        if manifest['priority_mode']!=mode:raise ValueError('Wrong experiment role')
        reports.append(verify(path))
        backend_hashes.append(manifest['source_sha256']['src/core301/research_runtime/m3b_runner.py'])
    if len(set(backend_hashes))!=1:raise ValueError('Experiments did not use the same execution backend')
    return {'overall_status':'M3C1_REAL_AGENT_PRIORITY_PASS','runs':reports,
            'medical_superiority_claimed':False,'dynamic_timing_implemented':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('real');p.add_argument('baseline_a');p.add_argument('baseline_b');a=p.parse_args()
    print(json.dumps(accept(a.real,a.baseline_a,a.baseline_b),indent=2))
