"""Fixed candidate payloads and backend-only delivery evidence.

This module does not grant permission to execute a protocol. The V2 protocol
book and runtime remain authoritative. No diagnostic is an Agent observation.
"""
import math
import re

from core301.pulse.injury_adapter import scalar

PROTOCOL_ID = "albuterol.single90.bronch04.phase2.1"
AUDIT_REQUESTS = (
    ("diagnostic.InspiratoryRespiratoryResistance", {"Category":"Physiology", "PropertyName":"InspiratoryRespiratoryResistance", "Unit":"cmH2O s/L"}),
    ("diagnostic.ExpiratoryRespiratoryResistance", {"Category":"Physiology", "PropertyName":"ExpiratoryRespiratoryResistance", "Unit":"cmH2O s/L"}),
    *(("diagnostic.Albuterol."+comp+"."+prop, {"Category":"LiquidCompartment", "CompartmentName":comp,
       "SubstanceName":"Albuterol", "PropertyName":prop, "Unit":"ug"})
      for comp,prop in (("InhalerMouthpiece","Mass"),("Airway","MassDeposited"),("LeftAlveoli","MassDeposited"),("RightAlveoli","MassDeposited"))),
)


def fixed_steps():
    """Fresh dictionaries matching the local official 4.3.2 scenario."""
    return [
        {"EquipmentAction":{"InhalerConfiguration":{"Configuration":{
            "Substance":"Albuterol", "MeteredDose":scalar("Mass",90,"ug"),
            "NozzleLoss":scalar("0To1",.04), "SpacerVolume":scalar("Volume",500,"mL")}}}},
        {"PatientAction":{"ConsciousRespiration":{"Command":[
            {"ForcedExhale":{"ExpiratoryReserveVolumeFraction":scalar("0To1",1), "ExhalePeriod":scalar("Time",3,"s")}},
            {"UseInhaler":{}},
            {"ForcedInhale":{"InspiratoryCapacityFraction":scalar("0To1",1), "InhalePeriod":scalar("Time",12,"s"),
                             "HoldPeriod":scalar("Time",3,"s"), "ReleasePeriod":scalar("Time",5,"s")}},
        ]}}},
    ]


def spontaneous_candidate_steps():
    """Separately preregistered candidate, not an alias for the official chain.

    Dose/nozzle/spacer unchanged. The InhalerModel itself handles UseInhaler;
    no forced vital-capacity breathing or backend-selected dose is introduced.
    Calling this payload builder does not open a CaseRuntime protocol.
    """
    return [fixed_steps()[0], {"PatientAction":{"ConsciousRespiration":{"Command":[{"UseInhaler":{}}]}}}]


def log_times(log_text, message):
    """Parse actual Pulse log timestamps; missing/unparseable is not time zero."""
    found=[]
    for line in log_text.splitlines():
        if message not in line:
            continue
        match=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*\(s\)",line)
        if match:
            found.append(float(match.group(1)))
    return found


def delivery_evidence(state, log_text, submitted_at_s):
    """Observe delivery separately from accepted and downstream drug response."""
    actuations=[t for t in log_times(log_text,"Inhaler actuated!") if t>=submitted_at_s-1e-6]
    removals=[t for t in log_times(log_text,"Inhaler removed!") if t>=submitted_at_s-1e-6]
    diagnostics=state.get("diagnostics",{})
    masses={k:v for k,v in diagnostics.items() if k.startswith("diagnostic.Albuterol.")}
    mass_seen=any(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in masses.values())
    common=state.get("inhaler",{}).get("Common",{})
    commands=state.get("actions",{}).get("ConsciousRespiration",[])
    result={"actuation_times_s":actuations,"removal_times_s":removals,"actuation_count":len(actuations),
            "actual_drug_presence_confirmed":mass_seen,"drug_diagnostics_ug":masses,
            "device_state":common.get("State"),"airway_mode":state.get("airway_mode"),
            "breathing_commands_active":bool(commands),"completion_scope":"single_administration_and_device_sequence",
            "clinical_recovery_claimed":False,"exact_lung_dose_claimed":False}
    if "Already processing a Substance Inhalation, ignoring this command" in log_text:
        return "UNKNOWN",{**result,"error":"NATIVE_INHALATION_COMMAND_IGNORED"}
    if len(actuations)>1:
        return "UNKNOWN",{**result,"error":"UNEXPECTED_REPEAT_ADMINISTRATION"}
    if len(actuations)==1 and mass_seen:
        if len(removals)==1 and removals[0]>=actuations[0] and common.get("State")=="Off" and state.get("airway_mode")=="Free" and not commands:
            return "COMPLETED",result
        return "ACTIVE",result
    if not actuations and commands and log_text:
        return "ACTIVE",{**result,"delivery_phase":"awaiting_actual_trigger"}
    return "UNKNOWN",{**result,"error":"ADMINISTRATION_NOT_CONFIRMED"}
