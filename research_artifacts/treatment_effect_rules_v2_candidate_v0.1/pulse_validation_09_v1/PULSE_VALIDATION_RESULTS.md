# V2E-09真实Pulse验证结果

**本轮2支原生实验均完整完成并归档。原锁定AST输出：M=false、F=false、I；安全状态UNRESOLVED。14/14已有首轮真实AST输出：10 E、3 P、1 I、0 NOT_EVALUABLE、0未完成。**

**关键限制：09的I由E1证据检查失败触发，具体为660.02秒置管瞬间的流率读数缺测。已有原生记录显示积血下降及自动停止，不能把该I解释为已证明治疗无效。14/14完成输出也不代表14条全部验收通过。**

## 实际执行

|分支|实际仿真终点(s)|墙钟(s)|状态|
|---|---:|---:|---|
|hemothorax_s0.8_Control|959.9999999994169|138.289|ARCHIVED|
|hemothorax_s0.8_Treatment|959.9999999994169|52.385|ARCHIVED|

- campaign：`hemothorax_09_v1`；Pulse 4.3.2，男性Soldier，Left Hemothorax Severity=0.8。Control与Treatment共享已固定的治疗前状态，患者、原Manifest、动作、采样与规则SHA均未修改。
- 运行前确认08停止仅限制该批自动继续，无全局执行禁止。本轮新授权及新campaign通过原门控；08的P、暂态HR异常、UNRESOLVED和原始文件均未变。
- 保留1500秒墙钟上限，没有必要调整。现有09路径原生步长/事件0.02秒；公共指标1秒；E1每秒及660.02秒动作点，共302条。没有把09误改成07/08的每步完整状态序列化。
- 只运行本轮2支；无H00、其他伤情、自动重试或新审批；未改代码、AST、阈值、患者或Manifest。

## 动作、机制和评价结果

|检查项|实际证据/结果|
|---|---|
|停源动作|实际659.9999999996897秒，Hemothorax Severity=0，accepted=true|
|胸管动作|实际660.0199999996897秒，Left TubeThoracostomy 30 mL/min，accepted=true|
|停源状态|660.02秒之后全部E1采样source_action_active=false；停源后源流率读数缺测，未补零|
|实际引流|积血27.776852 mL下降至−0.0031481481514185365 mL；661–715秒55个活动胸管采样流率为30 mL/min|
|原生自动停止|715.56秒日志明确记录Left Tube Thoracostomy has removed all blood. Setting flow rate to 0.|
|停止后|源与胸管均不活动，残余量稳定；保留原始微小负残值，不裁剪|
|E1_complete|false；ACTIVE_TUBE_EVIDENCE_MISSING_OR_CONFLICTING|
|M / F|false / false|
|原AST研究等级|I，errors=[]；未手动改为E、P或NOT_EVALUABLE|
|独立安全状态|UNRESOLVED，Na新数值触发导致SAFETY_REVIEW_REQUIRED|

**E1失败精确位置**：56条tube_action_active=true记录中，仅第一条660.0199999996897秒的tube_flow_mL_min为null；后55条为30。旧E1检查要求所有活动胸管记录流率均为30，因此返回false，适配层将其作为布尔事实传给原AST，令M/F失败。源流率302条中301条缺测；胸管流率247条为null（其中246条胸管未活动、1条活动瞬间）。缺测均原样保留。

这揭示了“动作瞬间流率可用性—E1布尔失败—疗效I”的解释缺口。现有执行及归档链路完成，但完整E1机制目标未被证据契约确认。后续若处理该问题，应另行核查读数可用时刻和缺测语义；本轮不删除该点、不填30、不改判、不重跑。

## 治疗前后及对照

末窗为原AST的900–960秒，实际61个公共采样。

|指标|治疗前|Treatment末窗均值 [最小, 最大]|Control末窗均值|
|---|---:|---:|---:|
|胸腔积血 (mL)|27.776852|-0.003148 [-0.003148, -0.003148]|40.276852|
|VT (mL)|460.268382|463.482856 [463.386646, 463.580572]|459.915342|
|SpO₂ (%)|97.326660|97.345479 [97.343538, 97.346814]|97.298424|
|PaO₂ (mmHg)|89.135340|89.603259 [89.579579, 89.625043]|89.011484|
|MAP (mmHg)|94.112869|94.841215 [94.817005, 94.851151]|94.746417|
|CO (L/min)|5.977382|6.084530 [6.078562, 6.088904]|5.957840|
|HR (/min)|84.478095|83.210635 [83.142503, 83.276691]|85.053150|
|Na (mEq/L)|144.565114|145.105097 [145.045061, 145.165112]|145.105964|
|Hb (g/dL)|14.894709|14.864375 [14.860965, 14.867780]|14.864876|
|pH|7.410155|7.411809 [7.411513, 7.412123]|7.409853|

- 按原始积血值计算，末窗减少100.011333711%，超过100%的极小部分来自原生负残值，不能解释为额外清除。20%/90%积血减少条件通过；末窗每点绝对残余≤1 mL通过；自动停止条件通过。这里比较的是胸腔积血量，不是出血率。
- VT全窗最低为基线的100.677488%，满足≥90%。
- 基线SpO₂=97.326660%、PaO₂=89.135340 mmHg，原AST选择氧合维持模式；末窗SpO₂、PaO₂均不低于基线，维持条件通过。M及F未通过的根源是E1_complete=false，并非氧合或积血减少不足。
- 相对Control，SpO₂末窗平均高0.047054个百分点，PaO₂高0.591775 mmHg。Control终点积血41.665741 mL，仍在增长。

## 安全与停止

- Na基线144.565114 mEq/L，约878秒起出现83个高于既定145 mEq/L复核界限的采样，终点145.165112。Control末窗Na也升高，但没有因此豁免Treatment。
- 原生事件保留：Hypernatremia, MinimalHemothorax, StartOfCardiacCycle, StartOfExhale, StartOfInhale。五类严重否决事件为空，必需安全指标缺测为空；独立状态UNRESOLVED，不宣称临床安全。
- 驱动在完整归档并计算I后触发既有安全复核停止并返回非零退出码，不是原生仿真中断。两支均已完成，本轮没有后续实验；停止标记原样保存。

## 完整性、复算与路径

- Control30项、Treatment27项归档文件SHA全部通过；执行回执、适配层校验通过，原AST离线复算与归档结果逐项一致。每支治疗后事件15,001条，严格递增且间隔0.02秒；E1 302条。原始数据完整保存不意味着所有原生测量均可用，上述流率缺测单列。
- 1326份保护文件SHA未变，含08全部异常证据、原健康参考、规则、AST/参数、患者、Manifest及执行代码。锁定规则SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。
- 本轮复用已有测试通过的代码，没有重复跑Mock或把旧离线测试计为本轮新验证。实际预检见`PREFLIGHT.json`；真实复核脚本及结果见`verify_results.py`、`REAL_EVIDENCE_CHECK.json`。
- 命令、实际墙钟耗时及退出码：`RUN_RESULTS.json`；日志：`native_execution.log`和各分支`.run.log`；机器可读结果：`RESULTS.json`；E1问题及原AST子条件：`MECHANISM_DETAILS.json`。

原生证据根目录：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/hemothorax_09_v1/`，下有`hemothorax_s0.8_Control/`及`hemothorax_s0.8_Treatment/`。

- 原始指标：`raw_requests.jsonl`、`capture/observations.jsonl`；事件：`raw_native_events.jsonl`、`capture/events.jsonl`。
- 原生机制：`E1_samples.json`、`E1_evidence.json`、初态/治疗前态/终态、`pulse.log`；动作：Treatment的`raw_actions.jsonl`。
- 封存与评价：`execution_receipt.json`、`SHA256.json`、`evaluation_manifest_V2E-09.json`、`evaluation.json`、`review_disposition.json`。

## 14条首轮真实AST输出汇总

|等级/状态|规则编号|数量|
|---|---|---:|
|E|01、02、03、04、05、06、10、11、13、14|10|
|P|07、08、12|3|
|I（有E1缺测解释限制）|09|1|
|NOT_EVALUABLE|无|0|
|未完成|无|0|

既有13条沿用已归档结果，本轮只新增09。**14/14指完成首轮真实执行及AST输出，不代表14条疗效通过、E1问题已解决或临床有效性得到认证。** 已停止，无新增实验或规则修改。
