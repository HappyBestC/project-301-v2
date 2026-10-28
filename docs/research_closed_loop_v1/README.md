# 最小真实科研数据闭环 V1

日期：2026-10-19。**RESEARCH_CLOSED_LOOP_V1_PASS**，仅指本轮单场景执行、共享记账、真实观测和正式评价入口连接符合验收要求；评价结果为 **NOT_EVALUABLE**，未获得E/P/I，不代表临床成功。

场景为 StandardMale，RightLeg 外出血 Severity=0.4；60秒施伤，180秒执行 `control_external_bleeding`，480秒终点。计划是合法 `301.treatment.complete.1` 单动作计划，使用原有研究控源代理将同源Severity设为0；不模拟现实外科手术。研究资源为同地点medic令牌1，无耗材和持续设备。

## 实际入口

在新科研工程目录执行：

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
python -B -m core301.research_runtime.runner
```

默认新建UUID run；也可 `--run-id 新的唯一名称`。已有目录拒绝重用，不能借此重放治疗。必须启用原有activate脚本设置独立Pulse绑定，不依赖原横向工程。只支持单run、单伤员和上述一个固定动作序列；不接受任意场景或原生参数覆盖，不调用真实LLM。

本轮真实完成run：[run_summary.json](../../experiments/results/minimal_closed_loop/external-source-control-native-002/run_summary.json)。原生结果与全部文件校验清单在[结果目录](../../experiments/results/minimal_closed_loop/external-source-control-native-002)。只读验证：

```bash
python -B -m core301.research_runtime.verify experiments/results/minimal_closed_loop/external-source-control-native-002
```

## 分层验收

|层次|结果|本轮证据|
|---|---|---|
|场景初始化|PASS|正式V2执行器加载固定初态、60秒RightLeg .4、180秒就绪；runtime/initialization_result.json|
|治疗前观测|PASS|真实13个公开字段与4个内部诊断；observations.jsonl首帧|
|完整计划|PASS|原CompletePlan与Provider实际接收值逐字段一致；treatment_plan.json / agent_received_plan.json|
|资源调度|PASS|原Fixed Provider→schedule_complete→同一M2-A原子预留；dispatch_result.json|
|执行就绪|PASS|onsite任务具备treatment_ready_at_s；coordinator.begin_usage通过，资源版本推进|
|Pulse治疗|PASS|一次原生治疗accepted=true；原生同源控源确认；execution_receipt_final.json|
|资源记账|PASS|medic预留→使用→有证据释放；终态available=1、consumed=0；resource_events.jsonl|
|治疗后观测|PASS|180—480秒共301帧；末60秒61帧；每帧保留真实时间和单位|
|正式评价入口调用|PASS|现有adapter.py子进程exit=0，stdout原样归档；evaluation_call.json|
|合法E/P/I结果|PARTIAL|原适配器拒绝MANIFEST_PATIENT_INPUT，返回NOT_EVALUABLE；没有伪造对照或评分|
|实验导出|PASS|31个run内文件SHA只读核验通过；[核验结果](validation/native_evidence_check.json)|

评价缺口包括StandardMale与独立Soldier输入不一致、无合法匹配Control、无独立执行证据合同、观察导出尚非独立适配器完整branch格式。当前入口首先在患者SHA处拒绝，未继续计算M/F；`minimum/complete/grade=null`是不可评价语义，不是I或预设评分。

## 本轮验证

全量非原生回归实际执行：**1043 passed，0 failed，26 deselected**（包含当时新增15项，不与旧1028相加）。之后增加Runner拒绝Fake证据入口测试，最终针对性集：**17 passed，0 failed**；另补初始化失败导出测试；没有把最终17项写成全量1045重新通过。详见[TEST_REPORT.md](TEST_REPORT.md)。

首次run-001未激活Pulse绑定，在加载PyPulse前失败，未执行治疗；该失败保留。run-002采用正式activate环境成功，不是重试未知治疗。旧001的`real_pulse=true`是早期“请求原生模式”的标记缺陷，不是执行证据；之后源码拆分native_execution_requested与成功初始化后的real_pulse。该原始失败文件未回写，详见测试报告。

## 导航

- [场景选择](SCENARIO_SELECTION.md)
- [数据流与字段](DATA_FLOW.md)
- [执行桥接与回执](EXECUTION_BRIDGE.md)
- [观测与评价](OBSERVATION_AND_EVALUATION.md)
- [测试与真实运行证据](TEST_REPORT.md)
- [限制及后续建议](LIMITATIONS.md)

未修改既有934个文件，未改冻结配置、原Prompt、原执行器、M2账本或锁定规则；仅新增集成模块、测试、结果及文档。没有开发M3、真实LLM十二动作生成、重规划或Unity。工作到此停止。
