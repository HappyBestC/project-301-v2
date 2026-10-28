from core301.contracts.treatment import TreatmentPlan as V1Plan
from core301.pulse.injury_adapter import scalar
from core301.pulse.treatment_adapter import TreatmentAdapter as V1Adapter
from core301.runtime.v2.errors import V2Error
from .protocol_book import ALLOWED_ACTIONS, protocol_id
from .proxy_adapter import ProxyAdapter


class TreatmentAdapter:
    def convert(self, action, source, validated_protocol):
        expected = protocol_id(source.injury_type, action.action_type)
        if validated_protocol != expected or action.action_type not in ALLOWED_ACTIONS[source.injury_type]:
            raise V2Error("PROTOCOL_MISMATCH", "Adapter requires the validated fixed protocol")
        if action.action_type.startswith("control_"):
            return ProxyAdapter().convert(action, source)
        if action.action_type == "supplemental_oxygen":
            return {"PatientAction": {"SupplementalOxygen": {"Device": "NasalCannula",
                "Flow": scalar("VolumePerTime", 0.5, "L/min"), "Volume": scalar("Volume", 425, "L")}}}
        if action.action_type in ("chest_tube", "inhaled_albuterol"):
            raise V2Error("ACTION_NOT_OPEN", "Reserved action cannot be adapted for execution")
        # Reuse V1 fixed payloads. Its paired-MV validator needs the preceding INT.
        sequence = ([{"action_type": "intubation"}] if action.action_type == "mechanical_ventilation" else [])
        sequence.append(action.model_dump())
        return V1Adapter().convert(V1Plan(patient_id=source.patient_id, actions=sequence))[-1]
