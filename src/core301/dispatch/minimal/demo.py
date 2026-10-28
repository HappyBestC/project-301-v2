"""python -m core301.dispatch.minimal.demo --output <new directory>"""
import argparse
import json
from pathlib import Path
from .api import build_input, load_cases, load_config, make_tasks, read, CONFIG
from .models import Schedule
from .coverage import SUMMARY_KEYS
from .validation import validate_schedule


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('runs/medical_resources_v1_demo'))
    parser.add_argument('--schedule',type=Path,default=CONFIG/'example_schedule_120.json')
    parser.add_argument('--horizon-min',type=float,default=120)
    parser.add_argument('--observation-time-min',type=float,default=60)
    args=parser.parse_args()
    resources,mapping=load_config();cases=load_cases();context=build_input(resources,mapping,cases,horizon_min=args.horizon_min,observation_time_min=args.observation_time_min)
    schedule=read(args.schedule);result=validate_schedule(context,schedule)
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'dispatch_input.json',context)
    write(args.output/'schedule_schema.json',Schedule.model_json_schema())
    write(args.output/'schedule.json',schedule)
    write(args.output/'task_requests.json',make_tasks(context,schedule['selections']))
    write(args.output/'validation.json',result)
    write(args.output/'observation_summary.json',result.get('observation_summary'))
    write(args.output/'planning_summary.json',result.get('planning_summary'))
    write(args.output/'occupancy.json',result['projected_occupancy'])
    write(args.output/'inventory_changes.json',result['projected_inventory_changes'])
    write(args.output/'candidate_requirements.json',[{'patient_id':p['patient_id'],'plans':p['candidate_plans']} for p in context['patients']])
    print(json.dumps({**{k:result[k] for k in SUMMARY_KEYS},'fully_verified':result['fully_verified'],'known_constraints_passed':result['known_constraints_passed'],
          'conflicts':len(result['conflicts']),'unchecked_codes':sorted({x['code'] for x in result['unchecked']}),
          'occupancy_records':len(result['projected_occupancy']),'inventory_records':len(result['projected_inventory_changes']),
          'output':str(args.output.resolve())},ensure_ascii=False,indent=2))
    return 1 if result['conflicts'] else 0

if __name__=='__main__':raise SystemExit(main())
