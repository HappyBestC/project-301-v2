# 数据流和可复核文件

每个 run 独立目录：`experiments/results/m3a_real_treatment_agent/<run_id>/`。只有实际到达的阶段才有相应证据文件。

| 阶段 | 实际来源和产物 |
|---|---|
| 预检 | preflight.json；配置存在、本地绑定、请求上限；run_manifest.json 记录版本和身份 |
| 初始化 | 原 CaseRuntime.prepare；StandardMale、60 秒 RightLeg .4、180 秒决策；runtime/initialization* |
| 真实观测 | observations.jsonl 首帧；agent_input.json 仅从本帧白名单和授权 registry 生成 |
| 模型调用 | llm_request.json 记录参数、消息、Prompt SHA、UTC 请求时间；llm_response.json 为真实服务响应，错误另存 llm_error.json |
| 解析 | treatment_decision.json；不修复原始 JSON、不替换动作 |
| 合同 | complete_plan.json / treatment_plan.json；decision_validation.json 关联 decision_id、plan_id、action_instance_ids |
| 调度 | dispatch_input.json、agent_received_plan.json、agent_resource_view.json、dispatch_result.json；onsite Fixed 提案和真实账本结果 |
| 执行 | execution_events.jsonl、runtime/execution_journal.json、execution_receipt*.json、native_action_results.json；共享身份与 runtime 身份别名及 allocation_ids |
| 资源 | resource_events.jsonl、resource_final.json；预留、使用、接受/未知、证据释放 |
| 治疗后 | 原采样 1 秒一次至 480 秒，总计 301 帧（含治疗前 180 秒帧）；诊断仅供后端/评价 |
| 评价 | 原 evaluation 调用、manifest、stdout/stderr、evaluation_result.json；不改变 RESEARCH_RULESET_V1_LOCKED |
| 汇总 | run_summary.json 的八个阶段和实际调用标记；SHA256.json 索引所有 run 文件 |

决策 ID 在 manifest/validation/summary 中，plan_id 链接调度与执行，action_instance_id 链接原生别名和 allocation；SHA 索引防止将不同 run 的输入、响应和执行混为一条轨迹。

`real_llm` 表示已收到服务响应文件，`llm_request_attempted` 单独表示发起尝试，`real_pulse` 表示成功初始化，`pulse_treatment_submitted` 根据真实 action_results 的 treatment phase 判断。接受回执不等于医学成功。只有决策、合同、资源、执行、观测、正式评价入口全部完成，才会输出 M3A_REAL_AGENT_EXECUTION_PASS；评价仍可 NOT_EVALUABLE。

先前 m3a-native-preflight-001 没有 agent_input、LLM 响应、计划、调度或治疗帧。用户配置后另建 m3a-real-agent-001 完成所有阶段；两个 run 保持独立，不用历史 native-002 填补证据。
