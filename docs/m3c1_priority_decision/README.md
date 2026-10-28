# M3-C1 真实优先级 Agent

2026-10-19（Asia/Shanghai）。本轮实现真实优先级 Agent → 严格排序准入 → M2资源申请 → 对应患者原生Pulse治疗的因果链。阶段最终状态 **M3C1_REAL_AGENT_PRIORITY_PASS**，见 [聚合验收](validation/acceptance.json)；单run运行时的保守 PARTIAL 标识不替代独立聚合验收。

新增 MultiPatientPriorityInput、MultiPatientPriorityDecision、PriorityDecisionProvider、FixedPriorityProvider、LLMPriorityDecisionProvider 和 PriorityResearchRun。三个模式共享原 M3-B episode；旧 M3-B 默认 A 优先仍可使用，新运行路径不固定获胜患者。完整源码清单、架构图与时序图见 [ARCHITECTURE](ARCHITECTURE.md)。

## 实际入口

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
# 下列命令每次创建新UUID目录；不要重复真实调用来追求特定排序
python -m core301.research_runtime.m3c1_runner --mode offline_test --priority-mode fixed_A_first
python -m core301.research_runtime.m3c1_runner --mode offline_test --priority-mode fixed_B_first
python -m core301.research_runtime.m3c1_runner --mode dual_native --priority-mode llm_priority
# 只读最终核验，不调用LLM或Pulse
python -m core301.research_runtime.m3c1_accept \
  experiments/results/m3c1_priority_decision/m3c1-real-priority-001 \
  experiments/results/m3c1_priority_decision/m3c1-fixed-a-native-001 \
  experiments/results/m3c1_priority_decision/m3c1-fixed-b-native-001
```

原生固定策略同样使用 `--mode dual_native` 和对应 `--priority-mode`。真实模式读取已有 `.env` / 环境变量，SDK retries=0、timeout=60秒、每run最多一次正式排序调用，没有第二个Treatment LLM。单run核验入口为 `core301.research_runtime.m3c1_verify`，离线证据须加 `--offline`。

## 实际决策

真实run：[m3c1-real-priority-001](../../experiments/results/m3c1_priority_decision/m3c1-real-priority-001/run_summary.json)。请求及响应模型标识均为 **gpt-6-sol**，实际调用一次。服务报告 prompt_tokens=2322、completion_tokens=235、total_tokens=2557，费用未提供为null。模型标识按配置服务响应记录，不额外推断底层服务商身份。

模型收到两个真实患者在180秒的HR、RR、SpO₂、SBP、MAP，各自单位/缺测状态/采样时间；授权RightLeg外出血；各自已冻结控源计划摘要及Catalog的medic×1需求；M2完整只读初始快照（medic可用1）和版本0；run、全局时刻与“仅排序”权限。隐藏Severity、内部机制和评价数据不进入模型请求。

[模型原始响应](../../experiments/results/m3c1_priority_decision/m3c1-real-priority-001/llm_response.json)中的 content：

```json
{"schema_version":"301.resource.priority.m3c1.1","run_id":"m3c1-real-priority-001","simulation_time_s":180.0,"resource_state_version":0,"decision_type":"prioritize","ordered_patient_ids":["m3c1-real-priority-001-A","m3c1-real-priority-001-B"],"reasoning_summary":"Both patients have identical known injuries, observations, and bleeding-control plans. The evidence does not distinguish urgency; ordering is an arbitrary tie-break with the single medic resource noted.","refusal_reason":null}
```

模型选择A优先，未被宿主替换。M2实际先处理A，A获得medic，B得到真实RESOURCE_IN_USE，只有A的原生Worker提交治疗。不能据此声称排序具有医学优越性。

| 全局时间 | 真实run关键事件 |
|---|---|
| 0秒 | 两个独立spawn Worker，各自StandardMale状态 |
| 60秒 | 各自按原冻结协议施加RightLeg外出血 |
| 180秒 | 同步采样；唯一LLM决定A→B；严格校验通过 |
| 180秒 | M2先预留A的medic；B返回RESOURCE_IN_USE；A真实治疗一次 |
| 181秒 | 两者同步采样；A原回执source_control_confirmed、源移除且出血率0；释放medic |
| 181秒 | B等待期间仍真实推进并出血；新版本/新幂等键重查获配 |
| 181秒 | B被UNVALIDATED_TIMING阻断；取消未用预留，不提交治疗 |
| 480秒 | 两者各301帧；medic归还，无未解决分配；正式评价保留NOT_EVALUABLE |

固定A和固定B各另跑一份原生实验，用同一执行代码验证两个方向；反向策略使B获得资源并执行、A等待。真实模型仍按其实际选择A执行。

[测试报告](TEST_REPORT.md)记录本轮实测数量、SHA/身份核验与原有功能回归；[LIMITATIONS](LIMITATIONS.md)说明未实现能力及C2前置条件。本轮止于C1。
