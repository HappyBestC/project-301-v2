"""Fixed Frozen thoracic pattern + manual plan, with real native Pulse branches."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ruamel.yaml import YAML
from core301.contracts.casualty import CasualtyInput
from core301.contracts.treatment import TreatmentPlan
from core301.paths import PROJECT_ROOT, FROZEN_ROOT
from core301.pulse.injury_adapter import InjuryAdapter
from core301.pulse.observation_projector import ObservationProjector
from core301.pulse.session import PulseSession
from core301.runtime.case_runtime import write_json
from .config import load_config
from .counterfactual import CounterfactualTreatmentEvaluator


def semantic_state_hash(state):
    # Native protobuf JSON map order is not stable across serializations.
    canonical = json.dumps(json.loads(state), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()


def demo_inputs():
    with (FROZEN_ROOT / "配置/battle_injury_patterns.yaml").open(encoding="utf-8") as stream:
        patterns = YAML(typ="safe").load(stream)["patterns"]
    pattern = next(p for p in patterns if p["pattern_id"] == "penetrating_thoracic_injury")
    casualty = CasualtyInput(patient_id="counterfactual_thoracic", injuries=pattern["injuries"])
    plan = TreatmentPlan(patient_id=casualty.patient_id, actions=[
        {"action_type": "occlusive_dressing", "side": "Left"},
        {"action_type": "chest_tube", "side": "Left"},
    ])
    return casualty, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config/treatment_evaluation.yaml")
    parser.add_argument("--runs-dir", type=Path, default=PROJECT_ROOT / "runs")
    args = parser.parse_args()
    config = load_config(args.config)
    casualty, plan = demo_inputs()
    run_dir = args.runs_dir.resolve() / ("counterfactual_" + uuid4().hex)
    run_dir.mkdir(parents=True, exist_ok=False)
    session = PulseSession(casualty.patient_id)
    summary = {"status": "running", "run_dir": str(run_dir), "llm_used": False}
    write_json(run_dir / "input.json", casualty)
    write_json(run_dir / "treatment_plan.json", plan)
    write_json(run_dir / "evaluation_config.json", config)
    try:
        import PyPulse
        summary["pulse_version"] = PyPulse.__version__
        session.initialize(run_dir / "live_pulse.log")
        session.apply_injury_actions(InjuryAdapter().convert(casualty))
        session.advance_time(60)
        projector = ObservationProjector()
        before = projector.project(session.patient_id, session.get_simulation_time(), session.read_requested_data())
        state_hash = semantic_state_hash(session.serialize_state())
        actions_before = [dict(a) for a in session.action_results]
        write_json(run_dir / "decision_observation.json", before)
        result = CounterfactualTreatmentEvaluator(config).evaluate(session, plan)
        after = projector.project(session.patient_id, session.get_simulation_time(), session.read_requested_data())
        state_after_hash = semantic_state_hash(session.serialize_state())
        unchanged = state_hash == state_after_hash and before == after and actions_before == session.action_results
        if not unchanged:
            raise RuntimeError("live session isolation verification failed")
        write_json(run_dir / "treatment_evaluation.json", result)
        write_json(run_dir / "live_after_evaluation.json", after)
        summary.update(status="completed", decision_time_s=before.simulation_time_s,
                       live_time_after_s=after.simulation_time_s, live_unchanged=unchanged,
                       live_state_sha256_before=state_hash, live_state_sha256_after=state_after_hash,
                       snapshot_sha256=result.snapshot_sha256, overall_effect=result.overall_effect,
                       injury_action_results=session.action_results,
                       same_snapshot=result.branch_origins["treatment"].snapshot_sha256 == result.branch_origins["control"].snapshot_sha256)
        print(f"Pulse {PyPulse.__version__}; decision time: {before.simulation_time_s:.6f}s")
        print(f"Snapshot saved/restored in memory: {result.snapshot_sha256}")
        for item in result.branch_results:
            directory = run_dir / f"horizon_{item.horizon_s:g}s"
            directory.mkdir()
            write_json(directory / "comparison.json", item)
            for name in ("treatment", "control"):
                branch = getattr(item, name)
                write_json(directory / f"{name}_observation.json", branch.observation)
                print(f"+{item.horizon_s:g}s {name}: observation @{branch.observation.simulation_time_s:.6f}s, {branch.episode_state}")
            for metric in item.metric_comparisons:
                print(f"  {metric.metric_name}: T={metric.treatment_value:.6g}, C={metric.control_value:.6g}, {metric.effect}")
            print(f"  effect: {item.effect} ({item.effect_reason})")
        print(f"Overall effect: {result.overall_effect}; calibration: {config.calibration_status}")
        print(f"Live session after evaluation: {after.simulation_time_s:.6f}s, full state unchanged")
        print(run_dir)
    except Exception as exc:
        summary.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        session.close()
        write_json(run_dir / "run_summary.json", summary)


if __name__ == "__main__":
    main()
