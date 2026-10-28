# 冻结工程契约：301.patient_observation.frozen.v2

归档日期 2026-10-14；基线 301.observation.v2.engineering.baseline.1。工程归档完成，用户最终验收待确认，Runtime 未启用。

以下原文逐字保留 B1 后候选语义；其中候选版本、待审核字样属于来源记录，不将其静默改写为新的运行时 Literal。冻结标识由 VERSIONS.json 绑定该源码与 Schema 的 SHA；N1 已知例外要求必经 Python 语义校验和可信投影。

---

# PatientObservation v2 候选

状态：**CANDIDATE / REVIEW_REQUIRED / NOT_ACTIVATED**。候选版本 `301.patient_observation.candidate.v2.1`，不是 V2.1 Runtime 版本，也不是新的正式冻结版。

**15 项：5 项基础 + 10 项条件。** 沿用 v1 的 13 项；新增两个可授权实验室条件字段；ICP 移出新核心，但 v1 模型、Schema、投影与冻结文件完全不改。普通最小观察仍只包含 5 项基础指标，不默认把 15 项全发给 Agent。

| 字段 | 中文名称 | 单位 | Pulse 4.3.2 原生来源 | 层级/可见性 | 实际读取 |
|---|---|---|---|---|---|
| `vitals.heart_rate` | 心率 HR | 1/min | Physiology / HeartRate | 基础，固定存在 | 已回放，33933 个可用读数 |
| `vitals.respiration_rate` | 呼吸频率 RR | 1/min | Physiology / RespirationRate | 基础，固定存在 | 已回放，33933 个可用读数 |
| `vitals.pulse_oximetry` | 脉氧 SpO₂ | 1 | Physiology / PulseOximetry | 基础，固定存在 | 已回放，33933 个可用读数 |
| `vitals.systolic_arterial_pressure` | 收缩压 SBP | mmHg | Physiology / SystolicArterialPressure | 基础，固定存在 | 已回放，33933 个可用读数 |
| `vitals.mean_arterial_pressure` | 平均动脉压 MAP | mmHg | Physiology / MeanArterialPressure | 基础，固定存在 | 已回放，33933 个可用读数 |
| `circulation.cardiac_output` | 心输出量 | L/min | Physiology / CardiacOutput | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `respiratory.tidal_volume` | 潮气量 | mL | Physiology / TidalVolume | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `respiratory.inspired_oxygen_fraction` | 患者吸入氧浓度 FiO₂ | 1 | Physiology / FractionOfInspiredOxygen | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.hemoglobin_concentration` | 血红蛋白浓度 | g/dL | Substance / Hemoglobin / BloodConcentration | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.lactate_concentration` | 乳酸浓度 | mg/dL | Substance / Lactate / BloodConcentration | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.arterial_oxygen_pressure` | 动脉氧分压 PaO₂ | mmHg | LiquidCompartment / Aorta / Oxygen / PartialPressure | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.arterial_carbon_dioxide_pressure` | 动脉二氧化碳分压 PaCO₂ | mmHg | LiquidCompartment / Aorta / CarbonDioxide / PartialPressure | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.blood_ph` | 血液 pH | 1 | Physiology / BloodPH | 条件，须相关+授权+获得结果 | 已回放，33933 个可用读数 |
| `laboratory.aorta_carboxyhemoglobin_concentration` | 主动脉碳氧血红蛋白浓度 | g/dL | LiquidCompartment / Aorta / Carboxyhemoglobin / Concentration | 条件，须相关+授权+获得结果 | 已回放，29116 个可用读数 |
| `laboratory.aorta_sodium_concentration` | 主动脉血钠浓度 | mEq/L | LiquidCompartment / Aorta / Sodium / Molarity | 条件，须相关+授权+获得结果 | 已回放，29719 个可用读数 |

`Measurement` 继续仅含 value/status/observed_at_s；单位固定在本表与 metric_catalog.json，Schema 不让调用方传任意单位。缺测不填 0，未授权直接省略，已授权且相关但不可用仅在允许披露时 unavailable。旧采样时间保留，未来/负数/非有限/字符串/布尔时间拒绝；没有医学阈值、插值或裁剪。

新增字段是拟议授权类型，**不是当前真实临床检验已建模**。COHb 使用 Aorta/Carboxyhemoglobin/Concentration，g/dL，不是百分比，不与 CO Saturation 混名；血钠使用 Aorta/Sodium/Molarity，mEq/L，不冒充已实现采血、送检和实验室周转时延。二者需分别由宿主授予 CO 检验/电解质检验权限，并提供实际获得的结果；不能从已知伤情自动解锁。正式检验权限与结果获取调度尚待集成审查。

模型 OxygenSaturation 暂不进入 Agent 集合，因为现有证据仅证明内部模型量可读，并未建立对应合法测量场景。Aorta CO Saturation、血容量、精确出血/积血量、原生事件和源状态均不在 Agent Schema 中。PaO₂、PulseOximetry、模型 OxygenSaturation、Ambient O₂、患者 FiO₂ 和设备设定不可相互替换。

五类复合伤共用 patient_id 和仿真时间的一份模型；字段白名单以集合去重，不为每种伤情重复记录 HR/MAP/PaO₂。Schema 是结构约束，不是授权认证：发布入口必须使用候选 projector 和可信宿主 Access；从请求正文直接接受 Access 不在本方案允许范围。
