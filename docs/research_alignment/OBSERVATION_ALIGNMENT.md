# 十五项生理指标与 Runtime 状态

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

**结论：十五项已定义，有可信投影/历史采集回放依据；尚未全面接入当前 Runtime 并由真实 Treatment Agent 使用。**

材料：[docs/research_references/新版生理指标.md](../../docs/research_references/新版生理指标.md)；冻结目录：[research_artifacts/observation_v2_contract_freeze_v1.0/FINAL_FREEZE_REPORT.md](../../research_artifacts/observation_v2_contract_freeze_v1.0/FINAL_FREEZE_REPORT.md)。源码逐项核对 [src/core301/observation_candidate_v2/catalog.py](../../src/core301/observation_candidate_v2/catalog.py)、[src/core301/observation_candidate_v2/models.py](../../src/core301/observation_candidate_v2/models.py)、[src/core301/observation_candidate_v2/projector.py](../../src/core301/observation_candidate_v2/projector.py) 和冻结 `schemas/metric_catalog.json`、`schemas/FIELD_DEFINITIONS.json`。

## 精确字段与原生来源

状态列依次为“定义一致性 / 新版全链路接入”。分数单位1的 SpO₂/FiO₂ 是0—1，不是百分数；pH 的1为无量纲。

|精确字段名|单位|Pulse 请求来源|必填/条件|当前 Treatment 入口能力|状态|
|---|---|---|---|---|---|
|`vitals.heart_rate`|1/min|Physiology / HeartRate|基础必填|默认可投影/传入|MATCHED / PARTIAL|
|`vitals.respiration_rate`|1/min|Physiology / RespirationRate|基础必填|默认可投影/传入|MATCHED / PARTIAL|
|`vitals.pulse_oximetry`|1|Physiology / PulseOximetry|基础必填|默认可投影/传入|MATCHED / PARTIAL|
|`vitals.systolic_arterial_pressure`|mmHg|Physiology / SystolicArterialPressure|基础必填|默认可投影/传入|MATCHED / PARTIAL|
|`vitals.mean_arterial_pressure`|mmHg|Physiology / MeanArterialPressure|基础必填|默认可投影/传入|MATCHED / PARTIAL|
|`circulation.cardiac_output`|L/min|Physiology / CardiacOutput|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`respiratory.tidal_volume`|mL|Physiology / TidalVolume|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`respiratory.inspired_oxygen_fraction`|1|Physiology / FractionOfInspiredOxygen|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.hemoglobin_concentration`|g/dL|Substance / Hemoglobin / BloodConcentration|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.lactate_concentration`|mg/dL|Substance / Lactate / BloodConcentration|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.arterial_oxygen_pressure`|mmHg|LiquidCompartment / Aorta / Oxygen / PartialPressure|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.arterial_carbon_dioxide_pressure`|mmHg|LiquidCompartment / Aorta / CarbonDioxide / PartialPressure|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.blood_ph`|1|Physiology / BloodPH|条件授权|旧合同可表达，需宿主授权及结果|MATCHED / PARTIAL|
|`laboratory.aorta_carboxyhemoglobin_concentration`|g/dL|LiquidCompartment / Aorta / Carboxyhemoglobin / Concentration|条件授权|旧 Agent 合同不可表达；研究诊断可采集|MATCHED / PARTIAL|
|`laboratory.aorta_sodium_concentration`|mEq/L|LiquidCompartment / Aorta / Sodium / Molarity|条件授权|旧 Agent 合同不可表达；研究诊断可采集|MATCHED / PARTIAL|

五基础＋十条件＝十五；无第十六项。ICP `neurologic.intracranial_pressure` 已从新版模型和 AGENT catalog 移除。旧 [src/core301/contracts/observation.py](../../src/core301/contracts/observation.py) 与 [src/core301/pulse/observation_projector.py](../../src/core301/pulse/observation_projector.py) 仍保留 ICP，是兼容路径；**若把旧合同称作 V2 正式核心合同会产生 MISMATCH**，本次未发现新版十五项目录偷偷加回 ICP。

## Measurement 与可见性

`Measurement` 在 `contracts/observation.py` 复用：available 必须有有限数值和 observed_at_s；unavailable 的 value 必须 null，时间可保留实际采样时刻或为 null；字段 absent 与 unavailable 不同。Number/Time 校验拒绝非法数值；新模型拒绝未来样本与越界分数。不能把缺测补零或把当前模拟时间冒充历史采样时间。

新版 `projector.Access` 由可信宿主提供。可见集合 = BASIC ∪ authorized∩relevant∩(results_obtained∪disclose_unavailable)。条件指标只有授权、相关且结果取得才发布 available；明确授权展示缺测才发布 unavailable；伤情名称或治疗资源充足不自动授权检测。真实检测申请、周转时间、监测设备和结果到达事件未统一接入。

COHb 为 Aorta Carboxyhemoglobin 的 **质量浓度 g/dL**，`aorta_co_saturation` 是另一诊断量，不能重命名当 COHb 百分比。V2E-13 的下降百分比是浓度相对基线变化。血钠为 Aorta Sodium Molarity，单位 **mEq/L**，不是 mg/dL。FiO₂ 生理采样、环境 O₂ 和设备设定 O₂ 是三个量，不可直接互换。

## PatientObservation 与 EvaluationObservation 隔离

新版 PatientObservationV2 只有患者ID、时间及十五项公开指标组，没有 Severity 真值、原生隐藏诊断、对照或疗效等级。EvaluationObservationV2 是研究后台时序容器，额外包含 diagnostics、events、actions、source_snapshots、gaps 和 evidence_path，不能直接发给 Agent。`EvaluationFrame` 限定 INTERNAL 白名单，患者身份一致、帧严格递增、证据时间非递减、同刻冲突拒绝；动作缺乏同刻顺序时明确记 gap。

注意：新版 EvaluationObservation 的结构**不自带完整配对 control / 健康参考 / 锁定规则 manifest**。`replay.py` 的历史文件回放与独立规则适配器的配对证据体系分离；材料关于对照/机制的描述不能解释成它已成为十四规则 Runtime 输入。该连接 PARTIAL。

## Projector 能力与真实消费方

旧 ObservationProjector 从请求样本生成旧 PatientObservation；默认仅五基础，条件字段最多使用旧合同的九项（包括 ICP）。新版 projector 是对 `row.values` / `row.diagnostics` 的可信投影函数，**不是自行发起十五项原生请求的实时采集服务**。

原生源代码具有对应请求：旧 REQUESTS 的十三个保留字段；[src/core301/pulse/v2/exposure_session.py](../../src/core301/pulse/v2/exposure_session.py) 的 COHb/Na 诊断；[src/core301/runtime/v2_1/native_backend.py](../../src/core301/runtime/v2_1/native_backend.py) 的公共十三项及内部诊断。它们证明原生来源可请求，历史回放证明部分分支实际采集过，不证明所有病例/时刻/Provider都收到十五项。

[src/core301/agent/llm_provider.py](../../src/core301/agent/llm_provider.py): `LLMTreatmentProvider.create_plan` 验证旧 AgentCaseContext，传入 patient_id、known_injuries、patient_observation，输出旧八动作 TreatmentPlan。[src/core301/context/builder.py](../../src/core301/context/builder.py) 和 [src/core301/runtime/v2/case_runtime.py](../../src/core301/runtime/v2/case_runtime.py): `observe/build_context` 仍依赖旧 ObservationProjector / AgentCaseContext。没有新版15字段 Provider 消费路径。两个新实验字段可能位于暴露/组合后台诊断，不等于已进入模型上下文。

因此可确定“默认五项，旧条件指标按宿主授权可能增加”，不能确定某个真实付费模型会话到底收到了哪些条件字段：本轮无该会话完整请求证据，实际线上消费集合 UNVERIFIED；十五项完整消费明确尚未接通。

## 三项状态重新核查

|状态|档案/源码证据|当前判断|
|---|---|---|
|ARCHIVE_VERIFIED|VERSIONS engineering_archive=VERIFIED；FINAL_FREEZE_REPORT记录归档核验|MATCHED：历史归档状态仍成立；不等于本轮重验全部大型原始数据|
|USER_ACCEPTANCE_PENDING|VERSIONS user_acceptance=PENDING；ACCEPTANCE_PENDING.md|MATCHED：未发现已登记的新验收；本次用户说“完成新版契约”不视为授权自动激活|
|NOT_ACTIVATED|runtime_activated=false；实际 Runtime/Provider 继续导入旧合同|MATCHED：源码调用关系支持未激活结论|

冻结标识为 `301.patient_observation.frozen.v2` / `301.evaluation_observation.frozen.v2`，运行源码仍使用 candidate.v2.1。[research_artifacts/observation_v2_contract_freeze_v1.0/VERSIONS.json](../../research_artifacts/observation_v2_contract_freeze_v1.0/VERSIONS.json) 明确说明这是一对档案名称/来源版本绑定，未执行运行时迁移；不是本轮应直接修的字符串错误。

档案既有验证记录是207执行、205通过、2项已知N1失败；不能写成207全通过。B1时间顺序修正有历史回放依据：33,933原始采样、26,690复合帧等来自原报告，不是本轮新采样。N1是JSON Schema无法完整表达Python语义校验，实际接入必须使用可信投影和Python校验器；仅schema通过不足以认定合法。
