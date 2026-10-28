# V2E-07/09 真实 Pulse 验证结果

日期：2026-10-17。使用Pulse 4.3.2原生引擎，新campaign：`chest_07_09_v1`。

## 实际结果

本轮实际启动 **1支** 原生实验，完整完成 **0支**。07 Control触发既有600秒墙钟上限，被Supervisor终止（exitcode=-15），状态`ABORTED`。最后完整原始生理采样为 **353.999999999968秒**，最后原生事件采样为 **354.6399999999674秒**，未达到480秒终点。按任务要求立即停止，未重试、未运行07 Treatment或09分支。

|分支|执行状态|M/F|AST疗效等级|安全状态|
|---|---|---|---|---|
|07 Control|原生已执行，超时ABORTED|不可计算|无；执行失败摘要NOT_EVALUABLE，不是AST治疗等级|UNRESOLVED|
|07 Treatment|NOT_ATTEMPTED|未计算|未生成|未评价|
|09 Control|NOT_ATTEMPTED|未计算|未生成|未评价|
|09 Treatment|NOT_ATTEMPTED|未计算|未生成|未评价|

不能从未治疗、未完成的Control推断胸封效果；没有Treatment/Control完整配对和末窗，不能输出07的E/P/I。09引流、自动停止、残余积血和VT未获得本轮原生结果。验证覆盖仍为 **10/14**，没有推进到12/14。

## 实验配置与停止原因

- Manifest及SHA预检通过，动态患者、伤情、采样和规则校验通过，不需要H00。
- 07：Left Open Severity=0.6，60秒起病，原计划180秒胸封、480秒评价。本次是Control，因此没有提交救助动作。
- 09（未运行）：Left Hemothorax Severity=0.8，660秒停源、660.02秒胸管30 mL/min、960秒评价。
- `driver.py:response()`在07路径每0.02秒调用`serialize_state()`并解析完整状态以提取通路证据。日志持续记录`SerializingToString`，进度明显慢于普通采样分支；本次明确阻塞是Supervisor的600秒墙钟上限。性能根因尚未专项剖析，不把推断冒充已定位的代码缺陷。
- 墙钟上限、采样频率、原生时间步及实验参数均未改变。没有降低证据要求、补造终点、复制历史结果或自动重试。

## 异常与原始证据

- 原生事件名称：['Antidiuresis', 'Hypoxia', 'StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale', 'Tachycardia', 'Tachypnea']。
- Hypoxia、Tachycardia、Tachypnea均完整保留。既定五类严重否决事件未记录，但数据仅覆盖部分窗口，不能宣称完整安全检查通过。
- 已保存356条原始请求采样和17734条原生事件记录；治疗前状态、初始化状态、伤情动作回执、通路/胸腔高频片段及日志保留。
- 强制终止后没有完整终态、完整Evaluation输入或正常完成的执行回执；不将部分归档包装为成功实验。
- `research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/chest_07_09_v1/open_s0.6_Control/`：原始文件、`pulse.log`、`raw_requests.jsonl`、`raw_native_events.jsonl`、`capture/`、`supervisor_failure.json`、`execution_failure_summary.json`、`lifecycle.json`、`SHA256.json`。
- 日志：`native_07_Control.log`；精确命令：`RUN_COMMANDS.txt`，其中后三条仅为原计划，**未执行**。当前运行ID不可重跑。

## 规则口径说明

用户任务中的09“出血率降低20%/90%”与锁定规则表描述不一致。原AST的`V2E-09.volume_reduction_min_pct=20`及`volume_reduction_full_pct=90`作用于`blood`（残余胸腔积血量，mL），不是源流率。完整条件要求积血**绝对值**全窗≤1 mL。后续应沿用原AST，源流率/胸管流率单独报告，缺测不填零；本轮未修改规则。

## 完整性与后续阻塞

- 1110份代码、规则、AST、参数、患者等保护文件SHA未变；未修改执行代码。失败归档23份文件SHA核验一致。
- 既有驱动预检通过；本轮没有运行Mock替代原生实验，也没有开展无关回归或规则研究。
- 后续最小工作是定位并处理0.02秒完整状态序列化路径的运行成本/墙钟预算适配，保持既定观测语义和原始数据不变；修复核验后使用新运行ID再开展实验。当前失败记录必须保留。
- 本轮已停止，无自动补跑、无其他规则实验、无正式评分权限变更。
