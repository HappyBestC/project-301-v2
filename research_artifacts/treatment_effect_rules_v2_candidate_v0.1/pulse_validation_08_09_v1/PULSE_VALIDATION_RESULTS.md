# V2E-08/09 真实Pulse验证结果

**实际完成08的Control和Treatment两支，均480秒、ARCHIVED；08为P。触发现有安全复核停止，09两支未启动。总体13/14：10 E、3 P、0 I、1未完成（09）。未宣称14/14完成。**

## 执行范围与停止语义

- 07旧campaign的P、HR异常、UNRESOLVED及归档均保持不变。检查现有`Runner.gate`、`run`、`execute_supervised`：停止的是该批次自动继续，没有持久的全局禁止。依据本轮明确授权，新建`chest_08_09_v1`，未修改门控。
- 原生Pulse版本4.3.2，男性Soldier，Left Closed TensionPneumothorax Severity=0.6，沿用原Manifest与共享治疗前状态；180秒穿刺减压，480秒评价。
- 完全复用现有驱动及锁定V1.0 AST；本轮没有修改执行代码、规则、阈值、患者或Manifest，也没有新增审批。H00绑定验证通过，复用此前真实健康数据，没有重跑。
- 原驱动发现08治疗后新的HR数值触发，设置`SAFETY_REVIEW_REQUIRED`、`automatic_continuation_allowed=false`，故依照用户“出现现有安全停止条件立即停止”要求未启动09。不是因P而停止，也没有自动创建另一个campaign绕过本轮停止。

## 实际分支

|分支|仿真终点(s)|墙钟(s)|状态|
|---|---:|---:|---|
|closed_s0.6_Control|479.9999999998534|1102.006|ARCHIVED|
|closed_s0.6_Treatment|479.9999999998534|1057.576|ARCHIVED|
|hemothorax_s0.8_Control|—|—|NOT_ATTEMPTED|
|hemothorax_s0.8_Treatment|—|—|NOT_ATTEMPTED|

两支08均在1500秒墙钟预算内完成。每支circuit、pleural、events各15,001行，时间严格递增，保持0.02秒频率。末窗高频机制数据3,001点，公共生理数据61点。没有降低精度、重试或覆盖历史记录。

## 原AST结果

|规则|M|F|AST研究等级|独立安全状态|
|---|---|---|---|---|
|V2E-08|true|false|P|UNRESOLVED，SAFETY_REVIEW_REQUIRED|
|V2E-09|未计算|未计算|未运行，不赋予E/P/I或NOT_EVALUABLE|未评价|

08针刺动作于180.00000000001828秒执行，accepted=true；`endpoint_needle_patent_proxy=true`。终态`LeftNeedleToLeftPleural`与最后高频通路原始记录一致，原生阻力数据为：`{"Resistance": {"Value": 100, "Unit": "cmH2O s/L", "ReadOnly": true}, "ResistanceBaseline": {"Value": 1.0197162129779282e+95, "Unit": "cmH2O s/L"}}`。适配器核实阻力等于锁定needle目标且低于基线，证明限定端点通畅代理成立；不能据此宣称漏气源修复。

|指标|治疗前|Treatment末60秒均值 [最小, 最大]|Control末60秒均值|
|---|---:|---:|---:|
|SpO₂ (%)|96.064954|96.788642 [96.746520, 96.820613]|84.976388|
|PaO₂ (mmHg)|62.089168|83.711091 [83.647011, 83.744476]|38.826379|
|MAP (mmHg)|88.222617|93.890701 [93.819413, 93.969302]|77.329718|
|HR (/min)|134.050034|103.057072 [102.976827, 103.129173]|192.600000|
|VT (mL)|324.051641|430.715358 [430.393810, 431.177509]|369.428985|
|左胸膜腔绝对压力 (cmH₂O)，1Hz摘要|1033.714247|1029.546430 [1028.150869, 1030.926591]|1036.565029|
|左胸膜腔容积 (mL)，1Hz摘要|1520.558595|1364.913995 [1268.651567, 1492.161124]|1782.834104|
|PaCO₂ (mmHg)|42.843612|39.761740 [39.640751, 39.883672]|43.231546|
|pH|7.386523|7.416038 [7.414829, 7.417244]|7.382960|

相对Control，SpO₂末窗平均高11.812254个百分点、PaO₂高44.884712 mmHg。相对自身基线，SpO₂平均提高0.723689个百分点、PaO₂提高21.621922 mmHg。全窗MAP最小变化5.596796 mmHg。

## H00绑定与机制距离

采用`pulse_validation_12_recovery_v1/H00_BINDING.json`及其历史代码来源证明，绑定`reference_12_08_v1/H00`真实数据。患者、环境、原始SHA及提取算法均经现有验证器核验。以下区间已含预定义容限，仅使用一次，不解释为通用临床正常范围。

|机制指标|H00候选区间|基线到区间距离|末窗平均距离缩短|全窗最小距离缩短|
|---|---|---:|---:|---:|
|绝对压力 (cmH₂O)|[1024.847938, 1029.853243]|3.861004|92.590598%|69.806968%|
|容积 (mL)|[948.803394, 1410.632417]|109.926178|81.994686%|25.033336%|

**M成立；F唯一未满足的顶层AND条件是容积距离的全窗50%缩短要求**：最弱点仅25.033336%。压力全窗最弱点69.806968%，满足50%。氧合完整条件及全窗MAP条件均通过，不能用均值81.994686%的容积缩短替代全窗条件。详见调用原`calc.eval_node`得到的`MECHANISM_DETAILS.json`。

08实际50Hz末窗压力范围1028.149541–1031.018997 cmH₂O、容积1268.057981–1493.040405 mL；两者都不是全窗落入健康区间。基线距离均非零，无需也未伪造epsilon。

## 安全事件与09未执行原因

- HR基线134.050034/min；190–199秒共10个1Hz采样超过既定140/min复核阈值，峰值141.379405/min。末窗均值103.057072/min、终点102.976827/min，已不再触发，但原政策仍将新出现过的数值触发记录为停止复核。
- 五类严重否决事件为空，必需安全指标缺测为空；不将UNRESOLVED改成VETO，也不将暂态异常已解除解释为医学安全通过。
- 原生事件完整保留：Hypoxia, StartOfCardiacCycle, StartOfExhale, StartOfInhale, Tachycardia, Tachypnea。
- 09未施加伤情或治疗，没有E1、积血减少、自动停止或疗效结果。其既定660秒停源、660.02秒胸管、960秒评价及积血量20%/90%规则均未改动。
- 当前没有新发现的代码或性能技术阻塞；未完成09的直接原因是08触发本轮既定安全停止条件。未自动重试或扩大实验。

## 校验、来源与耗时

- 运行前核验Pulse版本、33支Manifest/18组配对、代码/输入SHA、H00绑定及新campaign门控，见`PREFLIGHT.json`。本轮未改代码，未重复运行上一轮104项离线测试，不把旧测试计为本轮新测试。
- 本轮真实证据检查：Control31项、Treatment28项归档文件SHA全部一致；执行回执及适配层通过；08原AST完整离线复算一致。1259份受保护文件SHA未变，包括07全部记录、旧H00、规则、AST/参数、患者、Manifest和执行代码。见`REAL_EVIDENCE_CHECK.json`。
- 锁定规则SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。
- 命令、每支耗时及退出码：`RUN_RESULTS.json`；控制台日志：`native_execution.log`、各支`.run.log`。Treatment非零退出码表示归档后的安全复核停止，不能误写成原生仿真失败。

原生证据根目录：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/chest_08_09_v1/`。

- `closed_s0.6_Control/`、`closed_s0.6_Treatment/`各含原始请求、原生事件、初态/治疗前态/终态、capture高频序列、pulse.log、执行回执及SHA256.json。
- Treatment另含raw_actions.jsonl、evaluation_manifest_V2E-08.json、evaluation.json、review_disposition.json。
- 机器可读指标与原AST结果：`RESULTS.json`；高频/完整性复核：`REAL_EVIDENCE_CHECK.json`；实际性能分项：两支原生目录的`collection_performance.json`。

## 14条总体完成情况

既有12条沿用已归档结果；本轮仅新增08，不重算或改变已有等级。

|研究等级|规则|数量|
|---|---|---:|
|E|01、02、03、04、05、06、10、11、13、14|10|
|P|07、08、12|3|
|I|无|0|
|未完成|09|1|

**已停止。研究等级不代表临床安全认证，未宣称14/14完成或正式规则临床验证通过。**
