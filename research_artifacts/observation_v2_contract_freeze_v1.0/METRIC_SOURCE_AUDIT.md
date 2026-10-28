# 指标来源与旧契约审计

| v1 字段 | 单位 | 新版处理 | 门控与来源审查 |
|---|---|---|---|
| `vitals.heart_rate` | 1/min | 沿用 | Physiology / HeartRate；基础固定存在 |
| `vitals.respiration_rate` | 1/min | 沿用 | Physiology / RespirationRate；基础固定存在 |
| `vitals.pulse_oximetry` | 1 | 沿用 | Physiology / PulseOximetry；基础固定存在 |
| `vitals.systolic_arterial_pressure` | mmHg | 沿用 | Physiology / SystolicArterialPressure；基础固定存在 |
| `vitals.mean_arterial_pressure` | mmHg | 沿用 | Physiology / MeanArterialPressure；基础固定存在 |
| `circulation.cardiac_output` | L/min | 沿用 | Physiology / CardiacOutput；相关、授权、结果获得三重门控 |
| `respiratory.tidal_volume` | mL | 沿用 | Physiology / TidalVolume；相关、授权、结果获得三重门控 |
| `respiratory.inspired_oxygen_fraction` | 1 | 沿用 | Physiology / FractionOfInspiredOxygen；相关、授权、结果获得三重门控 |
| `laboratory.hemoglobin_concentration` | g/dL | 沿用 | Substance / Hemoglobin / BloodConcentration；相关、授权、结果获得三重门控 |
| `laboratory.lactate_concentration` | mg/dL | 沿用 | Substance / Lactate / BloodConcentration；相关、授权、结果获得三重门控 |
| `laboratory.arterial_oxygen_pressure` | mmHg | 沿用 | LiquidCompartment / Aorta / Oxygen / PartialPressure；相关、授权、结果获得三重门控 |
| `laboratory.arterial_carbon_dioxide_pressure` | mmHg | 沿用 | LiquidCompartment / Aorta / CarbonDioxide / PartialPressure；相关、授权、结果获得三重门控 |
| `laboratory.blood_ph` | 1 | 沿用 | Physiology / BloodPH；相关、授权、结果获得三重门控 |
| `neurologic.intracranial_pressure` | mmHg | 移出 v2 核心，v1 保留 | Physiology / IntracranialPressure；不是当前十类核心设计依据 |

## 新候选和内部量

- COHb：已有 EXPOSURE_REQUESTS 请求 Aorta / Carboxyhemoglobin / Concentration（g/dL），已回放单伤 CO、低氧及全部复合分支的已记录读数。质量浓度不等同 CO 饱和分数，不生成临床 COHb%。
- Aorta CO Saturation：Aorta / CarbonMonoxide / Saturation（0～1）。Saturation.cpp:274–275 将 targetBoundCO_mM / totalHb_mM 赋值为 CO 饱和分数；不是 COHb 质量浓度，也不是溶解 CO 分压。
- 模型 OxygenSaturation：Physiology / OxygenSaturation（0～1）。BloodChemistryModel.cpp:168 从 Aorta O₂ 的 Saturation 设置；该模型量可读，不命名为临床绝对“真实血氧”。暂为评价器内部量。
- PulseOximetry：同文件 170–182 行，非心搏骤停时取 RightArm O₂，CO 活跃时加 RightArm CO Saturation；不能在 CO 暴露时当作与 Aorta O₂ Saturation 相同。完整源码和真实轨迹均已核查。
- Na：Aorta / Sodium / Molarity（mEq/L），是已有原生请求；CO/低氧单伤与复合已读，旧七类单伤 CSV 未采集 Na 不补造。
- 血容量：Physiology / BloodVolume（mL）；既有 ResearchPulseSession 诊断，内部真值。TotalHemorrhageRate、TotalHemorrhagedVolume、腹腔 Volume 同样受限。
- 血胸：Action / LeftHemothorax / TotalBloodVolume（mL）；LeftTubeThoracostomy / FlowRate（mL/min）；LeftHemothorax / FlowRate（mL/s）。注意不同流量单位，不把源流量和胸管流量混用；动作消失时可以 unavailable。
- 出血源：可信已存原生 ActiveActions 的状态快照，独立非数值证据；不从动作 accepted 直接推断控制成功。
- 原生事件：每 .02 秒检查、集合变化时记录的 active-events JSONL；另存完整原生日志。事件时间是采集读后语义，持续时间与首次发生时刻不混淆。动作回执为第三种独立证据。
- FiO₂：Physiology / FractionOfInspiredOxygen 是患者吸入结果；Ambient/Oxygen/VolumeFraction 是环境设置区室；机械通气/供氧设置是动作参数。三者不互填。

所有新 Agent 候选字段和 13 项沿用字段均在 30 个复合分支的 requests.json 中逐项核对，并实际回放，而非仅凭源码字段存在。源代码审计 SHA 见 validation/audited_source_sha256.json；原始读取证据 SHA、逐字段可用数量和分支缺口见 validation/used_evidence_sha256.json、replay_audit.json。不新增任何原生采集系统。
