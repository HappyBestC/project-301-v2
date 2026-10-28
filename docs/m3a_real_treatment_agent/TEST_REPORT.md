# 本轮测试与验收

2026-10-19（Asia/Shanghai）。最终状态 **M3A_REAL_AGENT_EXECUTION_PASS**。以下数字均为本轮实际运行，不引用历史测试作为当前结果。

| 检查 | 本轮结果 | 证据 |
|---|---|---|
| 新增 M3-A 测试 | 32 passed，0 failed | validation/m3a_tests.log |
| 原 research_runtime 定向回归 | 17 passed，0 failed；也包含在全量结果 | 本轮执行 pytest -q tests/research_runtime |
| 全量非原生回归 | **1077 passed，0 failed，26 deselected**；6 个既有 pkg_resources 弃用告警 | validation/full_regression.log |
| 离线 runner | draft/CompletePlan PASS_MOCK；无 API、无原生执行 | m3a-offline-001 |
| 首次真实预检 | BLOCKED at preflight；缺三个配置项，未请求模型、未初始化 Pulse | m3a-native-preflight-001、validation/native_preflight.log |
| 配置后真实实验 | **八阶段 PASS**；一个真实 LLM 请求、一个真实 Pulse 治疗 | m3a-real-agent-001、validation/real_agent_native.log |
| 原生与决策证据核验 | PASS；38 文件 SHA、301 帧、61 末窗帧、一次治疗、模型原文/计划/输入逐项一致 | validation/real_evidence_check.json |
| 文件完整性 | 原 833 个 src/config/research_artifacts 文件，仅 runner.py 改变；无删除；锁定 14 规则校验通过 | validation/change_audit.json |

32 项包含：五指标单位/缺测/白名单、身份/时刻/临床授权、严格 draft 与目标、越界/空/重复/非法顺序、非 JSON/围栏/重复 key、缺字段/额外字段、原生参数注入、版本错误、模型暂缓/拒绝、字段无损及宿主策略、真实 SDK 的 HTTP Mock 请求与响应留痕、usage 真实性、HTTP 错误/超时/空响应无重试及错误脱敏、模拟运行时与真实 M2-A/B/C 成功关联/资源短缺/解析失败/合同失败、离线无 live 依赖、预检失败导出和 run 不可复用。

HTTP Mock 和 SessionFaultFixture 只是离线测试。新集成用例直接以 Provider 返回 draft 建计划，不先构建固定计划。真实 API/Pulse 的证明来自单独的 m3a-real-agent-001，不能混称为 32 项单元测试中的真实调用。

原执行桥回归包含 unknown/rejected 隔离、同请求幂等、accepted 不足以释放、任务取消、非法 scope/依赖；全量包含 Treatment V1、M2-A/B/C、Pulse 适配和正式评价接口。26 个旧 integration 用例继续未运行。本轮独立真实 runner 不意味着该 26 项已运行。

全量回归之后新增了只读 m3a_verify 工具，实际对真实 run 执行并通过；此工具不进入运行链路。未把该命令额外计入 1077 项。

## 独立验收

| 决策通路 | 结果 |
|---|---|
| 真实 LLM 请求/响应 | PASS；请求/响应模型均 gpt-6-sol，usage 612+66=678，费用未提供 |
| 本次真实患者 Agent 输入 | PASS；来自 180 秒真实帧，五指标/单位/时间与请求一致 |
| 结构化动作选择 | PASS；服务原文提出 control_external_bleeding / RightLeg |
| CompletePlan 校验 | PASS；新 draft 直接构建正式合同，无旧八动作转换 |
| 失败拦截 | PASS_OFFLINE；非法输出不进入预留/治疗 |
| 决策留痕 | PASS；原文→解析→完整计划→调度全等校验，SHA 索引 |

| 执行通路 | 结果 |
|---|---|
| 完整计划 → M2-C | PASS；agent_received_plan 与模型动作构建的 CompletePlan 全等 |
| 原子资源预留 | PASS；SATISFIED，medic=1，任务 onsite ready |
| 真实 Pulse | PASS；180 秒提交一次控源，最终 COMPLETED 和 source_control_confirmed |
| 资源生命周期 | PASS；预留→使用→accepted→机制确认→释放，medic 可用数恢复 1，无耗材 |
| 治疗前后观测 | PASS；180—480 秒 301 帧，含治疗前首帧及 300 次推进后采样 |
| 正式评价调用 | PASS；原适配器退出码 0，结果 NOT_EVALUABLE，MANIFEST_PATIENT_INPUT |
| 证据归档 | PASS；38 文件 SHA 与身份关联核验 |

评价不可用仍因 StandardMale 与独立 Soldier 患者证据不匹配；无合法匹配对照等限制未改变。本次没有 E/P/I 结论，未放宽匹配条件、修改规则或补造对照。

## 最终问题逐项答复

1. 模型：gpt-6-sol，请求和服务回报一致；1 次真实请求，未重试。
2. 实际发送：合成 patient_id、180 秒时刻、授权 RightLeg 外出血；心率 75.322886、呼吸率 12.048193、SpO2 0.973863、收缩压 112.762291、平均动脉压 95.025363，含原单位/状态/时间。没有 severity 或内部诊断。
3. 原始输出：见 llm_response.json；完整 content 已原样列在 AGENT_INPUT_OUTPUT.md。
4. 模型选择：control_external_bleeding，compartment=RightLeg。
5. 模型生成 decision_type、actions/目标、简短解释、拒绝原因；宿主补身份、scope/severity、固定策略和依赖。
6. CompletePlan：正式 301.treatment.complete.1 校验通过。
7. Resource Scheduling Agent：Fixed 提案 onsite，team_id/ambulance_id/target_facility_id 均 null，没有第二个真实 LLM。
8. M2-A/B/C：成功预留 medic=1，resource_result.outcome=SATISFIED，预留时 state_version=1。
9. Pulse：真实执行一次模型选择动作，accepted=true，随后 COMPLETED，有控源机制确认。
10. 治疗前后数据：301 帧真实数据，末 60 秒 61 帧。
11. 正式评价器：已调用，NOT_EVALUABLE / MANIFEST_PATIENT_INPUT，无疗效等级。
12. 文件：experiments/results/m3a_real_treatment_agent/m3a-real-agent-001；先前失败和离线 run 分目录保留。
13. 测试：全量 1077 passed、0 failed、26 deselected；32 新测试和 17 定向回归均已含在其中，不能相加。
14. 阻断/兼容：本场景无执行阻断；单动作、五指标、内存账本、StandardMale/Soldier 评价证据限制仍在。单候选成功不证明复杂规划或资源优化。
15. 下一阶段：可开始独立的双伤员研究设计/开发；双患者时钟、共享实验协议、生命周期仍需另行实现和验证。本轮没有进入 M3-B/C。

用户自行填写配置后，宿主使用全新 run 完成已授权的真实实验，没有重放预检失败目录或新增审批。至此停止，等待下一阶段任务。
