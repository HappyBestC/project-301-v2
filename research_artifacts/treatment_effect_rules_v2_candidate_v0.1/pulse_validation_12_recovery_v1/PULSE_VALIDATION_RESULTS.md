# V2E-12 Condition最小修复与真实Pulse结果

日期：2026-10-17。新增原生实验仅1支：`dehydration_12_recovered_v1/dehydration_s0.4_Treatment`。未重跑H00或Control。

## 修复与旧证据恢复

- adapter.py新增精确规范化：仅删除Dehydration内恰好等于`{"Condition":{}}`的PatientCondition空元数据。Severity、其他字段、伤情种类和Conditions列表仍严格比较，原始字典不修改。
- driver.py新增仅限dehydration_s0.4_Treatment的旧Control引用：复用原始preparation_dehydration.0.4.json及其原始初态/治疗前状态。没有创建伪ARCHIVED分支。
- execution_evidence.py识别独立`301.dehydration_condition_recovery.v1`补充证据：要求原FAILED原因仅为INITIAL_CONDITION_MISMATCH、存在原COMPLETED记录、日志已关闭、原归档SHA和历史代码快照匹配，并继续执行原回执源、患者、时间和采样校验。该文件是离线恢复证明，不冒充原生执行时生成的回执。
- H00引用通过既有历史代码核验函数恢复代码版本绑定；新增绑定文件，不改旧H00及旧绑定，不改变参考提取算法。
- 19项针对性测试通过，涵盖Severity/伤情/非空元数据/额外字段、来源SHA、伪造完成时间、未来恢复、显式执行、H00代码版本、共享初态及真实旧Control。99项相关驱动回归通过（含32支Mock与18组比较），日志完整保存。

## 真实结果

H00健康总体液上界：40361.368827 mL。原Manifest男性Soldier、Dehydration Severity=0.4；180秒Saline 500 mL袋量、100 mL/min，480秒评价。末窗420–480秒，保留实际浮点时间。

|指标（单位）|治疗前|Treatment末窗均值 [最小, 最大]|Control末窗均值|
|---|---|---|---|
|CO (L/min)|5.663099|6.226065 [6.124184, 6.305998]|5.641479|
|MAP (mmHg)|94.616459|95.306125 [94.418071, 96.394546]|94.647465|
|BV (mL)|5257.074404|5716.570064 [5665.667231, 5767.449324]|5267.755372|
|fluid (mL)|38529.652211|38965.280664 [38917.241599, 39013.324786]|38523.006431|
|Na (mEq/L)|148.762101|149.153193 [149.101212, 149.205012]|149.571453|
|Hb (g/dL)|15.622934|14.367581 [14.240444, 14.496270]|15.591246|
|pH (1)|7.409323|7.416664 [7.416047, 7.417191]|7.408973|

- 相对H00上界的描述性总体液缺口（不是AST残余缺口基准）：1831.716616 mL；Treatment末窗缺口：{'mean': 1396.0881628955863, 'min': 1348.044040950219, 'max': 1444.127227970872, 'last': 1348.044040950219}。
- CO相对自身基线增幅：{'mean': 9.940950558218786, 'min': 8.14191620408793, 'max': 11.352427888389425, 'last': 10.764912993247252}%。不是将相对Control增量替代原规则。
- 动作accepted：[True]；原生执行时间：[180.00000000001828]。实际体液/血量变化与终态动作信息均保留；标称袋量不直接视作实际入体量。

|M|F|锁定V1.0 AST研究等级|独立安全状态|
|---|---|---|---|
|True|False|P|UNRESOLVED|

原生事件：['Antidiuresis', 'Hypernatremia', 'StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale']；严重事件：[]；必需安全缺测：[]。安全状态原因：PROFILE_MEDICAL_OWNER_EVENT_POLICY_PENDING。容量响应不代表高钠纠正，不宣称临床治愈。

## 证据与完整性

- 新原生数据：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/dehydration_12_recovered_v1/dehydration_s0.4_Treatment/`，包含原始采样、事件、动作、初态/终态、pulse.log、执行回执、评价Manifest及SHA。
- 独立恢复证据：CONTROL_RECOVERY.json、RECOVERY_CHECK.json、historical_code/；旧FAILED、旧SHA和H00均不变。
- 1084份保护文件SHA未变；新归档26份文件SHA验证通过；治疗结果用原AST复算一致。
- 不调整规则、AST、阈值、患者或实验配置；没有重试或运行07/08/09。

## F未满足的明确原因与动作生效

AST区分健康0秒参考与300秒上界：残余缺口使用`matched_healthy_total_fluid_mL`=40351.188116 mL计算；上界检查使用40361.368827 mL，不能混为一个数值。

- AST初始缺口：1821.535905 mL；完整目标要求末窗**每点**剩余缺口≤初始缺口10%，即≤182.153590 mL。
- 实际末窗缺口均值：1385.907452 mL，范围[1337.863330, 1433.946517] mL，未达到上述完整目标，故F=False。
- CO全窗≥5%、体液和血容量全窗增加≥100 mL均满足；体液全窗未超过H00上界，检查通过。
- 原生日志明确记录`[479.98(s)] Completed infusion of Saline`；终态输液动作已结束，结合体液与血容量实际上升，确认不只接口accepted。原始日志与终态保存，未由袋量反推实际入体量。
- Na由148.762101升至末窗均值149.153193 mEq/L，虽然低于Control的149.571453，仍不得宣称高钠已解除；Antidiuresis与Hypernatremia均保留。
- 本轮仅新增1支Treatment，成功ARCHIVED，无重试、无新的技术阻塞。真实研究评价覆盖由10/14推进至11/14，新增结果为P而非E。
