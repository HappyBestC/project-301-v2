# M3-C2 真实资源反馈与独立时序研究

2026-10-19（Asia/Shanghai）。本轮分开交付真实反馈控制与动态时序探索。最终分项状态及证据见 [验收报告](validation/acceptance.json)。原始run_summary记录独立核验前状态，不回写历史数据或SHA。

最终分项状态：

- 真实反馈：**M3C2_REAL_AGENT_FEEDBACK_PASS**，真实分支WAIT→DEFER。
- 时间审查与设计：**M3C2_TIMING_AUDIT_PASS**、**M3C2_TIMING_PROTOCOL_DESIGNED**。
- 独立原生技术探索：**M3C2_TIMING_EXPLORATORY_PASS**。
- 有限双患者动态执行：**M3C2_DUAL_PATIENT_DYNAMIC_EXECUTION_PASS**，仅独立新协议+Fixed反馈实验。
- 完整动态时序疗效适用性：**M3C2_TIMING_NOT_VALIDATED**，不生成正式E/P/I。

## 运行

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
# Fake Pulse + 真实M2，不调用API
python -m core301.research_runtime.m3c2_runner --mode offline_test
# 固定C1优先级 + 真实Feedback LLM，保持旧180秒协议；新run最多2次调用
python -m core301.research_runtime.m3c2_runner --mode feedback_native
# 独立新协议 + 自动技术预检 + 原生Pulse；明确Fixed反馈，不调用LLM
python -m core301.research_runtime.m3c2_runner --mode timing_exploratory
# 只读核验，不重新治疗或调用LLM
python -m core301.research_runtime.m3c2_verify experiments/results/m3c2_feedback_decision/m3c2-real-feedback-001
python -m core301.research_runtime.m3c2_verify experiments/results/m3c2_feedback_decision/m3c2-timing-exploratory-001
```

支持`--run-id`（已有目录拒绝复用）与`--priority-mode fixed_A_first|fixed_B_first`。真实反馈模式不接受Fixed反馈替换，其他模式明确标记其证据类型。

## 本轮实际模型决定

真实run：[m3c2-real-feedback-001](../../experiments/results/m3c2_feedback_decision/m3c2-real-feedback-001/run_summary.json)。配置及响应模型均为 **gpt-6-sol**，实际 **2次**；不自动重试、无第二个真实Priority Agent、无替代治疗生成。原文见 [llm_responses.jsonl](../../experiments/results/m3c2_feedback_decision/m3c2-real-feedback-001/llm_responses.jsonl)，解析结果见 [feedback_decisions.jsonl](../../experiments/results/m3c2_feedback_decision/m3c2-real-feedback-001/feedback_decisions.jsonl)。

| 次数/全局时间 | 实际输入与版本 | 实际输出 | 宿主实际行为 |
|---|---|---|---|
| 1 / 180秒 | B真实五指标、授权RightLeg伤情、固定控源计划、M2的RESOURCE_IN_USE和A的blocking allocation；当前账本V3 | KEEP_PLAN_AND_WAIT | 保留计划，登记实际释放事件条件，不重复申请 |
| 2 / 181秒 | B新真实观测、历史冲突、A真实释放事件、当前medic可用1、账本V5；旧时间准入false | DEFER_INSUFFICIENT_EVIDENCE | 明确暂缓本轮后续决策，不申请新资源，不给B治疗 |

模型第一次解释：

> M2 could not allocate the medic because the resource is currently in use; retain the pending plan and wait for an actual resource release event with a changed ledger version.

第二次解释：

> The medic is now available after an actual release, but timing admission is not allowed. A resource recheck cannot resolve that timing restriction, and no alternate plan or treatment time is authorized.

第二次refusal_reason：

> Timing admission for the pending action is unavailable; further decision attempts in this bounded experiment are deferred.

冲突Result保留发生时的版本，与当前V3/V5快照分开记录；A开始使用和执行确认也会推进账本版本。模型没有获准读取Severity、内部机制、未来生理轨迹或评价器内部信息。

服务真实usage：第1次3446 prompt / 430 completion / 3876 total；第2次3449 / 621 / 4070；合计7946 total。成本未提供为null。模型名称和usage按所配置服务记录，不推断底层服务商身份。

本轮全量非原生回归 **1182 passed、26 deselected、0 failed**，新增48项已包含其中。两份原生run独立核验通过：真实反馈66文件SHA，探索65文件SHA。旧26项native integration未运行。

## 两份原生实验不可混称

| 时间 | 真实Feedback旧协议run | 独立Timing探索run |
|---|---|---|
| 60秒 | 两患者按冻结伤情施伤 | 相同 |
| 180秒 | A获配并治疗，B真实冲突；真实模型WAIT | A获配并治疗，B真实冲突；Fixed WAIT |
| 181秒 | A控源确认并释放；真实模型DEFER，B不再申请/治疗 | A控源确认并释放；Fixed RECHECK，新M2确认后B按新协议治疗 |
| 182秒 | B仍未治疗，继续观察 | B源控确认并释放 |
| 480秒 | A治疗1次、B0次，两者各301帧 | A/B各治疗1次，两者各301帧 |

真实模型覆盖WAIT→真实释放唤醒→DEFER，**未覆盖真实LLM选择RECHECK/STOP**。RECHECK的控制效果由离线和明确Fixed的原生探索证明；STOP由离线测试证明。真实反馈run的B未治疗是模型合法暂缓且旧181秒不准入；不能把探索run的B治疗计入真实反馈run。

新协议为`301.research.dynamic_timing.m3c2.1`，仅180/181秒离散候选；通过独立技术预检后才进入原生探索，复用原执行器所有非时间约束。旧180秒协议和配置未扩展。详见 [时间审查](TIMING_PROTOCOL_AUDIT.md)、[新协议](DYNAMIC_TIMING_PROTOCOL.md)。

| 能力 | 实现/验证范围 |
|---|---|
| 真实资源反馈→LLM→控制行为 | 真实WAIT、事件唤醒、DEFER分支 |
| 新版本/新幂等请求RECHECK | 离线与Fixed原生探索；非真实LLM选择 |
| STOP取消未执行任务 | 离线；未知/在用资源保留 |
| 180/181新协议技术执行 | 独立探索run，不能冒充旧协议 |
| 其他延迟时点、替代动作、通用多轮重规划 | 未开放 |
| 正式动态疗效E/P/I与医学优越性 | 未验证，NOT_EVALUABLE |

[架构及源码清单](ARCHITECTURE.md)、[本轮测试报告](TEST_REPORT.md)、[限制与下一阶段条件](LIMITATIONS.md)。本轮完成后停止。
