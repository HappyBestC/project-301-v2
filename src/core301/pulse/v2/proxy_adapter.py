from core301.pulse.injury_adapter import scalar
from core301.runtime.v2.errors import V2Error

PROXY_TYPES = {"control_external_bleeding": ("external_hemorrhage", "External"),
               "control_internal_bleeding": ("abdominal_internal_hemorrhage", "Internal")}


class ProxyAdapter:
    def convert(self, action, source):
        if action.action_type == "control_hemothorax_bleeding":
            raise V2Error("ACTION_NOT_OPEN", "Hemothorax proxy is reserved; no business execution in phase 1")
        expected, native_type = PROXY_TYPES[action.action_type]
        if source.injury_type != expected or source.compartment != action.compartment or not source.active or not source.authorized:
            raise V2Error("TARGET_NOT_AUTHORIZED", "Proxy source mismatch")
        return {"PatientAction": {"Hemorrhage": {"Type": native_type, "Compartment": source.compartment,
                                                "Severity": scalar("0To1", 0)}}}
