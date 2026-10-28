"""Standalone bounded research demonstration, with mandatory explicit fixture opt-in."""
import argparse
import csv
import json
from pathlib import Path
from uuid import uuid4

from core301.agent.v2.manual_provider import ManualTreatmentProvider
from core301.pulse.observation_projector import BASIC, REQUESTS, ObservationAccess
from core301.pulse.v2.protocol_book import OPEN_INJURIES
from .case_runtime import CaseRuntime
from .resources import explicit_test_resources

PLANS={
    "external_hemorrhage":[{"action_type":"control_external_bleeding","compartment":"RightLeg"}],
    "abdominal_internal_hemorrhage":[{"action_type":"control_internal_bleeding","compartment":"Spleen"}],
    "open_pneumothorax":[{"action_type":"occlusive_dressing","side":"Left"}],
    "closed_tension_pneumothorax":[{"action_type":"needle_decompression","side":"Left"}],
    "respiratory_muscle_impairment":[{"action_type":"intubation"},{"action_type":"mechanical_ventilation"}],
    "impaired_alveolar_exchange":[{"action_type":"supplemental_oxygen"}],
    "dehydration":[{"action_type":"fluid_resuscitation"}],
}


def main(argv=None):
    parser=argparse.ArgumentParser(description="V2 phase-1 single-injury research demo; no production, Agent or E/P/I")
    parser.add_argument("--injury",choices=tuple(OPEN_INJURIES),required=True)
    parser.add_argument("--severity",type=float)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--research-fixture",action="store_true",help="Explicitly authorize finite test supplies; not production inventory")
    args=parser.parse_args(argv)
    if not args.research_fixture:parser.error("--research-fixture is mandatory; no resources are assumed")
    if args.output.exists():parser.error("output must be a new directory; never overwrite a journal")
    levels,location,expected=OPEN_INJURIES[args.injury]
    level=args.severity if args.severity is not None else (0.4 if 0.4 in levels else levels[0])
    if level not in levels:parser.error("severity is outside the fixed verified profile")
    run_id=uuid4().hex
    grants=frozenset(k for k in REQUESTS if k not in BASIC and not k.startswith("neurologic."))
    access=ObservationAccess(grants,grants,grants)
    rt=CaseRuntime("P001",args.output,run_id=run_id,mode="research",resources=explicit_test_resources(run_id,"P001"),access=access)
    rows=[];checkpoints={}
    try:
        injury={"injury_type":args.injury,"severity":level}
        if location:injury[location]=expected
        rt.prepare({"patient_id":"P001","injuries":[injury]})
        ticket=rt.build_context()
        (args.output/"authorized_context.json").write_text(ticket.public.model_dump_json(indent=2)+'\n')
        plan=ManualTreatmentProvider({"patient_id":"P001","actions":PLANS[args.injury]}).create_plan(ticket.public)
        rt.execute_plan(plan,request_id="manual-demo",context_ref=ticket.context_ref)
        for elapsed in range(301):
            if elapsed:rt.advance(1,reconcile=elapsed in (1,5,180,300))
            obs=rt.observe();row={"time_s":obs.simulation_time_s}
            for group,measurements in obs.model_dump(exclude_unset=True).items():
                if isinstance(measurements,dict):
                    row.update({group+"."+k:v["value"] for k,v in measurements.items()})
            rows.append(row)
            if elapsed in (1,5,180,300):checkpoints[str(elapsed)]={"active_events":rt.session.active_events(),"execution":rt.query("manual-demo")}
        result={"status":"completed_research_simulation","production_enabled":False,"post_s":300,"checkpoints":checkpoints,
                "execution":rt.query("manual-demo"),"formal_epi":None,"resource_mode":"explicit_research_fixture"}
        (args.output/"demo_result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({"status":result["status"],"output":str(args.output),"production_enabled":False}))
    finally:
        if rows:
            with (args.output/"observations.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        rt.close()


if __name__=="__main__":main()
