"""Offline MR5 draft example. Scene capabilities and route durations are explicit fixtures."""
import argparse
import asyncio
from pathlib import Path
from uuid import uuid4
from core301.paths import PROJECT_ROOT
from core301.pulse.observation_projector import BASIC, Sample, ObservationProjector
from core301.runtime.case_runtime import write_json
from .clock import SimulationClock
from .models import DispatchInput, DispatchProposal, CallContext, CallFailure
from .manager import ResourceManager
from .eta import FakeEtaProvider, EtaAdapter
from .providers import FixedDispatchProvider, LLMDispatchProvider
from .service import decide_dispatch
from .validation import DispatchError


def demo_input():
    observation = ObservationProjector().project("P-001", 45, {
        k: Sample(v, 45) for k, v in zip(BASIC, [100, 22, 0.94, 100, 75])
    })
    return DispatchInput.model_validate({
        "run_id": "RUN-DEMO", "patient_id": "P-001", "position": {"x": 10, "y": 0, "z": 20},
        "current_facility_id": None, "patient_observation": observation.model_dump(),
        "treatment_plan": {"patient_id": "P-001", "actions": [{"action_type": "fluid_resuscitation"}]},
        "facilities": [
            {"run_id": "RUN-DEMO", "facility_id": "FAC-001", "display_name": "演示救护站", "kind": "aid_station",
             "position": {"x": 100, "y": 0, "z": 200}, "capacity": 2, "supported_action_types": ["fluid_resuscitation"],
             "reserved_patient_ids": [], "admitted_patient_ids": []},
            {"run_id": "RUN-DEMO", "facility_id": "FAC-002", "display_name": "演示医院", "kind": "hospital",
             "position": {"x": 300, "y": 0, "z": 200}, "capacity": 1,
             "supported_action_types": ["fluid_resuscitation", "supplemental_oxygen"],
             "reserved_patient_ids": [], "admitted_patient_ids": []}],
        "ambulances": [{"run_id": "RUN-DEMO", "ambulance_id": "AMB-001", "display_name": "演示后送车",
                        "position": {"x": 0, "y": 0, "z": 0}, "active_task_id": None}],
        "medical_teams": [{"run_id": "RUN-DEMO", "team_id": "TEAM-001", "display_name": "演示配车小队",
                           "position": {"x": 20, "y": 0, "z": 20}, "supported_action_types": ["fluid_resuscitation"],
                           "active_task_id": None}],
    })


def demo_eta():
    return FakeEtaProvider({
        ("ambulance_to_patient", "AMB-001", 10, 0, 20): ("available", 12, None),
        ("patient_to_facility", "AMB-001", 100, 0, 200): ("available", 35, None),
        ("patient_to_facility", "AMB-001", 300, 0, 200): ("available", 70, None),
        ("team_to_patient", "TEAM-001", 10, 0, 20): ("available", 18, None),
    })


async def run_demo(args):
    directory = args.runs_dir.resolve() / ("resource_scheduling_" + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    data = demo_input().model_dump()
    data["run_id"] = directory.name
    for group in ("facilities", "ambulances", "medical_teams"):
        for resource in data[group]:
            resource["run_id"] = directory.name
    source = DispatchInput.model_validate(data)
    clock = SimulationClock(45)
    manager = ResourceManager(source, clock)
    eta = EtaAdapter(manager.snapshot, demo_eta(), manager.ensure_active)
    context = CallContext(call_id=uuid4().hex, run_id=source.run_id, patient_id=source.patient_id)
    summary = {"status": "running", "provider": args.provider, "eta_provider": "fake",
               "simulation_time_s": clock.now_s, "scene": "explicit_mock_fixture", "pulse_treatment_submitted": False}
    write_json(directory / "dispatch_input.json", source)
    write_json(directory / "call_context.json", context)
    write_json(directory / "resources_before.json", manager.snapshot())
    try:
        provider = (LLMDispatchProvider(enable_eta_tools=args.eta_tools) if args.provider == "llm" else
                    FixedDispatchProvider(DispatchProposal(patient_id=source.patient_id, mode="evacuation", team_id=None,
                                                           ambulance_id="AMB-001", target_facility_id="FAC-001")))
        response = await decide_dispatch(context, source, provider, eta.query_eta, ensure_active=manager.ensure_active)
        write_json(directory / "dispatch_response.json", response)
        if isinstance(response, CallFailure):
            raise DispatchError(response.error.code, response.error.message)
        write_json(directory / "dispatch_proposal.json", response.data)
        task = manager.accept(context, source, response.data)
        write_json(directory / "dispatch_task.json", task)
        write_json(directory / "resources_after.json", manager.snapshot())
        summary.update(status="completed", task_id=task.task_id, task_state=task.state, mode=task.mode,
                       eta_queries=len(eta.records), treatment_plan_unchanged=source.treatment_plan == manager.snapshot().treatment_plan)
        print(f"DispatchInput -> {len(eta.records)} ETA queries -> DispatchProposal -> backend validation -> DispatchTask")
        print(f"mode={task.mode}; state={task.state}; accepted_at_s={task.accepted_at_s:g}; no Pulse treatment submitted")
        for record in eta.records:
            result = record.get("result", {})
            print(f"ETA {record['query']['leg']}: {result.get('status')}, duration={result.get('travel_duration_s')}")
        print(directory)
    except DispatchError as exc:
        summary.update(status="failed", error_code=exc.code, error=str(exc))
        raise
    except Exception:
        summary.update(status="failed", error_code="DISPATCH_FAILED", error="demo configuration or provider failure")
        raise
    finally:
        write_json(directory / "eta_queries.json", eta.records)
        write_json(directory / "run_summary.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("fixed", "llm"), default="fixed")
    parser.add_argument("--eta-tools", action="store_true", help="opt in only if the compatible API supports tool calling")
    parser.add_argument("--runs-dir", type=Path, default=PROJECT_ROOT / "runs")
    args = parser.parse_args()
    if args.eta_tools and args.provider != "llm":
        parser.error("--eta-tools requires --provider llm")
    asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
