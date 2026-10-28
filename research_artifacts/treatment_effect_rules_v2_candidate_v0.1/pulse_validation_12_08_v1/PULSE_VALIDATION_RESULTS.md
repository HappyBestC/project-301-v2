# V2E-12/08 真实 Pulse 验证结果

Pulse 4.3.2；日期2026-10-17；campaign `reference_12_08_v1`。

## H00真实健康参考

未发现已有可复用的原生Soldier H00，本轮依原Manifest新运行1支。完整300秒，无伤情和治疗；180–300秒0.02秒采样，按原算法提取末尾10个完整稳定呼吸周期。原生执行归档、参考重算、SHA和技术绑定均通过，不新增审批机制。
- 原压力区间：[1025.8479376620605, 1028.8532434296983] cmH₂O（绝对压）；加一次容限后：[1024.8479376620605, 1029.8532434296983] cmH₂O。
- 体积候选区间：[948.8033940128515, 1410.6324174485344] mL。
- 健康总体液量：0秒40351.188116 mL；300秒上界40361.368827 mL；漂移10.180711 mL。体液质量kg未转换冒充体积。
- 原质量统计：{'period_cv': 0.0, 'pressure_mean_span': 6.561515010616858e-05, 'volume_mean_relative_span': 5.643764697376814e-06}；candidate_stable=True。
- 通过既有make_reference_binding/validate_reference_binding生成并核验H00_BINDING.json。12在运行前绑定同患者/环境/规则/算法及来源SHA；08具备所需健康参考字段，但未运行，不能声称08已完成实验身份匹配及参考复用验证。

## 实际执行分支

- `H00`：ARCHIVED；原始目录 `research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/reference_12_08_v1/H00/`。
- `dehydration_s0.4_Control`：FAILED；原始目录 `research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/reference_12_08_v1/dehydration_s0.4_Control/`。
- `dehydration_s0.4_Treatment`：NOT_ATTEMPTED；原始目录 `research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/reference_12_08_v1/dehydration_s0.4_Treatment/`。
- 08 Control/Treatment：0支，性能预检阻断。07、09及其他规则：0支。

## V2E-12（固定Severity=0.4）

为最少实验选择已预注册的Severity=0.4作为本轮单一固定Profile，在任何结果产生前固定；不代表0.2、0.6均已验证。Condition初始化，180秒Saline 500 mL袋量、100 mL/min，480秒评价，末窗420–480秒。

|规则|M|F|原AST研究等级|独立安全状态|
|---|---|---|---|---|
|12|未计算|未计算|未生成|未评价|
|08|未计算|未计算|未运行，不赋予等级|未评价|

## 08性能阻塞

driver.py response对open和closed执行同一0.02秒完整状态序列化分支。此前07 Control在600秒墙钟上限时仅完成约354秒，未达480秒。本轮未修复该性能路径，不能确认08可在现有限时内完成，因此按要求在原生启动前阻断08。没有重跑07、延长时限、降低采样频率或跳过通路机制证据。

## 完整性

1110份保护文件SHA不变；未修改执行代码、患者、Manifest、规则、AST或阈值。H00参考重算与绑定一致，H00及FAILED Control的归档SHA均通过；没有治疗AST结果可重算。原始请求、事件、状态、动作、日志、执行回执和SHA保留在各分支目录。无自动重试。

## 12新技术阻塞及停止结果

本轮实际执行2支原生实验：H00一支成功ARCHIVED；12 Control一支完成480秒仿真后在validate_data阶段FAILED；12 Treatment未启动，08两支未启动。没有重试。实际疗效覆盖仍为10/14，不能计入第11或第12条。

失败原因：`male_independent_validation_final_preparation_v1/adapter.py:94`直接比较Conditions字典。原生Dehydration多序列化了空元数据`PatientCondition: {Condition: {}}`，而Manifest省略它；两侧Severity均为0.4。只读差异核对证实除此空字段外内容一致，但未绕过门控、未重写原FAILED。后续最小修复应采用严格且保留伤情身份/Severity检查的规范化比较，并优先利用本次真实数据离线复核，不重复采集Control。

### 失败Control已保存的真实指标（不是治疗结果）

|指标|180秒锚点|420–480秒Control均值|
|---|---|---|
|CO (L/min)|5.663099|5.641479|
|MAP (mmHg)|94.616459|94.647465|
|BV (mL)|5257.074404|5267.755372|
|fluid (mL)|38529.652211|38523.006431|
|Na (mEq/L)|148.762101|149.571453|
|Hb (g/dL)|15.622934|15.591246|

相对H00健康上界的总体液缺口：锚点1831.716616 mL，Control末窗均值缺口1838.362396 mL。仅描述数值，不冒充完整规则认可的病例参考配对。

原生事件：['Antidiuresis', 'Hypernatremia', 'StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale']。执行失败安全状态为UNRESOLVED，未记录五类严重否决；异常不隐藏。M/F及E/P/I均未生成，执行失败摘要的NOT_EVALUABLE不等于治疗I。

H00已生成可追溯的患者专属技术参考附件。本轮12通过了运行前引用校验，但未完成病例级AST参考一致性验收；08仅具备可供后续绑定的健康压力/体积参考，尚未实际复用验证。无医学批准或安全认证声明。
