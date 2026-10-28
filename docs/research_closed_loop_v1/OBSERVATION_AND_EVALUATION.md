# 观测采集与锁定评价入口

## 真实采集

run `external-source-control-native-002`，治疗前180.00000000001828s，终点479.9999999998534s；公共采样每1秒，301帧，末60秒420—480窗口61帧。没有用单个终点代替评价窗口，也没有裁剪实际浮点时间。

原REQUESTS中除ICP之外的13项均请求，并由显式研究宿主授权、相关和结果取得集合投影：五项vitals、cardiac_output、tidal_volume、inspired_oxygen_fraction、Hb、lactate、PaO₂、PaCO₂、pH。每项保存value/status/observed_at_s、单位和原生来源；缺测保持null/unavailable。内部诊断来自原V2 DIAGNOSTICS：BloodVolume、TotalHemorrhageRate、TotalHemorrhagedVolume、AbdominalCavityVolume。

|真实字段|单位|治疗前|480秒终点|
|---|---|---|---|
|`vitals.heart_rate`|1/min|75.32288609|75.59654670|
|`vitals.mean_arterial_pressure`|mmHg|95.02536330|95.12681798|
|`circulation.cardiac_output`|L/min|5.60696366|5.61740064|
|`laboratory.hemoglobin_concentration`|g/dL|14.94533407|14.90851117|

出血率从1.3875565623723651 mL/s到0；原executor在181.0000000000188s确认同源不再活动且总出血率0，累计失血173.0659699721137mL。终点数值仅是描述性观测，**不据此自行评分E或宣布血容量恢复**。

## V2契约边界

本次研究导出使用原 `observation_candidate_v2.projector.project` 和 `EvaluationObservationV2` 做严格字段/时间语义校验；这是本场景局部导出适配，不修改全局版本或激活十五指标。COHb和Na未请求、未填0、未假定正常；ICP不进入该导出。

PatientObservation公开字段用于调度Provider；EvaluationFrame另带四项内部诊断。完整EvaluationObservation保存301帧和关联动作回执；事件转换/源快照没有从不充分数据推断，显式空列表并记录gaps，原生状态和事件快照另存。native_events.json为1秒快照，`complete=false`，不能冒充0.02秒完整事件史。安全状态保留UNRESOLVED。

## 实际规则调用

`research_runtime/evaluation.py`首先验证源规则与锁定副本、parameter_registry和definitions三项SHA。随后启动当前工程内未改动的：

`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/adapter.py`

其真实 `evaluate→assemble→manifest_plan` 使用原校验链。入口读取本次真实患者文件、事件证据SHA及尝试映射的V2E-01 manifest；不是复制简化评分器。`evaluation_call.json`记录命令、返回码0、适配器SHA、输入manifest SHA和模拟终点，stdout/stderr原样保存。

实际输出：`computation_state=NOT_EVALUABLE`、`formal_grade=null`、`errors=["MANIFEST_PATIENT_INPUT"]`、`subconditions={}`；最低目标M、完整目标F未被计算。此为原入口拒评，不是硬编码NE代替调用。

## 为什么不可评价

1. 当前正式Runtime加载StandardMale固定初态；原独立EXPERIMENT_MATRIX为Soldier患者配置，并要求不同来源及初始化证据。真实patient_input SHA不匹配，在manifest_plan首先拒绝。没有替换患者SHA、改名或沿矩阵的历史DataRoot访问原工程。
2. 未产生合法匹配Control；manifest.control=null，不能拿治疗前或历史不同患者轨迹当未治疗对照。
3. 没有独立adapter要求的execution evidence contract和完整branch证据。当前manifest是尝试接入证据描述，不冒充已通过其全部格式/来源校验。
4. 原生事件仅1秒快照，非完整步进史；这项缺口保留在导出中。

以上后续缺口由桥接如实列出；原入口本次首先返回的是患者来源错误，**不声称其已逐个运行了所有后续拒绝检查**。现有十四规则AST/阈值和grade谓词未改，M/F没有被绕过前置检查计算。V2E-01的P仍不适用；NOT_EVALUABLE不转I。

## 证据位置

- [真实观察](../../experiments/results/minimal_closed_loop/external-source-control-native-002/observations.jsonl)、[受控EvaluationObservation](../../experiments/results/minimal_closed_loop/external-source-control-native-002/evaluation_observation.json)
- [原执行确认](../../experiments/results/minimal_closed_loop/external-source-control-native-002/execution_receipt_final.json)
- [评价manifest](../../experiments/results/minimal_closed_loop/external-source-control-native-002/evaluation_manifest.json)、[实际调用记录](../../experiments/results/minimal_closed_loop/external-source-control-native-002/evaluation_call.json)
- [原始评价stdout](../../experiments/results/minimal_closed_loop/external-source-control-native-002/evaluator_stdout.json)、[汇总评价结果](../../experiments/results/minimal_closed_loop/external-source-control-native-002/evaluation_result.json)

后续若需合法E/P/I，最小工作是确定与正式scope相容的患者/参考证据入口、按原协议产生合法配对，并补齐原适配器要求的证据结构。不能仅新增Control后忽略患者不匹配，不能修改冻结阈值或将本次机制观察自行当E。
