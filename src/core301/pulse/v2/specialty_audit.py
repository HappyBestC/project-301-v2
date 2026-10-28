"""Read-only native mechanism audit, never an Observation or permission grant."""
from .albuterol import log_times
from .session import native_scalar


def hemothorax_evidence(state, diagnostics, log_text, side):
    if side not in ("Left", "Right"):
        raise ValueError("Exact native side required")
    actions=state.get("actions",{})
    tubes=[b for b in actions.get("TubeThoracostomy",[]) if b.get("Side")==side]
    sources=[b for b in actions.get("Hemothorax",[]) if b.get("Side")==side]
    volume=diagnostics.get("diagnostic."+side+"Hemothorax.TotalBloodVolume")
    leak=diagnostics.get("diagnostic."+side+"Hemothorax.FlowRate")
    stopped=log_times(log_text,side+" Tube Thoracostomy has removed all blood. Setting flow rate to 0.")
    return {"side":side,"source_action_active":bool(sources),"source_flow_mL_s":leak,
            "source_flow_valid":leak is not None,"residual_volume_mL":volume,
            "negative_native_residual":volume is not None and volume<0,
            "tube_action_active":bool(tubes),"tube_native_flow":native_scalar(tubes[0],"FlowRate") if len(tubes)==1 else None,
            "auto_stop_times_s":stopped,"auto_removal_observed":bool(stopped) and not tubes,
            "full_treatment_completed":False,"authorized_observation_endpoint":False,
            "interpretation":"Mechanism evidence only; no null-to-zero substitution or residual correction"}


def oxygen_evidence(state):
    matches=state.get("actions",{}).get("SupplementalOxygen",[])
    if len(matches)!=1:
        return {"state":"UNKNOWN","device":None,"remaining_oxygen_L":None}
    oxygen=matches[0]
    volume=native_scalar(oxygen,"Volume")
    device=oxygen.get("Device")
    return {"state":"ACTIVE" if state.get("airway_mode")==device and volume is not None and volume>0 else "UNKNOWN",
            "device":device,"native_flow":native_scalar(oxygen,"Flow"),"remaining_oxygen_L":volume,
            "clinical_safety_claimed":False,"treatment_completed":False}
