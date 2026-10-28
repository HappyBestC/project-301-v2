from core301.contracts.treatment import TreatmentPlan
from .injury_adapter import scalar


class TreatmentAdapter:
    def convert(self, plan: TreatmentPlan) -> list[dict]:
        plan = TreatmentPlan.model_validate(plan)
        result = []
        for action in plan.actions:
            kind = action.action_type
            category = "PatientAction"
            if kind in ("occlusive_dressing", "needle_decompression"):
                name = {"occlusive_dressing": "ChestOcclusiveDressing",
                        "needle_decompression": "NeedleDecompression"}[kind]
                body = {"Side": action.side, "State": "On"}
            elif kind == "chest_tube":
                name = "TubeThoracostomy"
                body = {"Side": action.side, "FlowRate": scalar("VolumePerTime", 30, "mL/min")}
            elif kind in ("fluid_resuscitation", "transfusion"):
                name = "SubstanceCompoundInfusion"
                body = {"SubstanceCompound": "Saline" if kind == "fluid_resuscitation" else "Blood",
                        "BagVolume": scalar("Volume", 500, "mL"),
                        "Rate": scalar("VolumePerTime", 100, "mL/min")}
            elif kind == "supplemental_oxygen":
                name = "SupplementalOxygen"
                body = {"Device": "NonRebreatherMask", "Flow": scalar("VolumePerTime", 15, "L/min"),
                        "Volume": scalar("Volume", 425, "L")}
            elif kind == "intubation":
                name, body = "Intubation", {"Type": "Tracheal"}
            elif kind == "mechanical_ventilation":
                category, name = "EquipmentAction", "MechanicalVentilatorPressureControl"
                body = {"MechanicalVentilatorMode": {"Connection": "On"}, "Mode": "AssistedControl",
                        "FractionInspiredOxygen": scalar("0To1", 0.21),
                        "InspiratoryPressure": scalar("Pressure", 13, "cmH2O"),
                        "PositiveEndExpiratoryPressure": scalar("Pressure", 5, "cmH2O"),
                        "RespirationRate": scalar("Frequency", 12, "1/min"),
                        "InspiratoryPeriod": scalar("Time", 1, "s"),
                        "Slope": scalar("Time", 0.1, "s")}
            else:
                raise ValueError(f"unsupported treatment {kind}")
            result.append({category: {name: body}})
        return result
