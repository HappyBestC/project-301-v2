# M3-A 真实 Treatment Agent 接入

2026-10-19（Asia/Shanghai）。当前状态 **M3A_REAL_AGENT_EXECUTION_PASS**：真实 `gpt-6-sol` 的单次决策经 CompletePlan 校验、M2-C 调度及 M2-A 预留进入真实 Pulse，完成控源、资源释放和 301 帧观测；正式评价器真实调用，返回 NOT_EVALUABLE。此状态表示单场景链路通过，不代表医学疗效有效。

## 运行

在 `/home/private/project-301-v2` 内：

```bash
source scripts/activate.sh
python -m core301.research_runtime.m3a_runner --mode offline_test
python -m core301.research_runtime.m3a_runner --mode real_agent_native
```

真实模式读取项目 `.env` 或已有环境变量中的 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`，不修改全局配置。每个新 run 最多一次决策请求，SDK retries=0，timeout=60 秒，max_tokens=1200；模型不支持请求参数时保留失败，不自动换模型或计划。预检检查配置和本地绑定；远端模型是否可服务由唯一决策请求确认，不额外发收费探测请求。

可传 `--run-id 全新名称`，已存在目录拒绝执行。默认 UUID。不要重用失败或未知执行 run 的目录。本次用户填写配置后使用新 run 完成真实实验，先前失败记录原样保留。

## 本次证据

- [真实成功 run](../../experiments/results/m3a_real_treatment_agent/m3a-real-agent-001/run_summary.json)：模型请求/响应、正式合同、原生执行、资源及评价完整归档。
- [只读证据核验](validation/real_evidence_check.json)：原始响应→draft→plan→实际调度无损；真实观测→输入→请求一致。
- [先前真实模式预检阻断](../../experiments/results/m3a_real_treatment_agent/m3a-native-preflight-001/run_summary.json)：三个配置项缺失；LLM 请求数 0，Pulse 治疗数 0，评价 NOT_RUN。
- [离线入口](../../experiments/results/m3a_real_treatment_agent/m3a-offline-001/run_summary.json)：明确 MOCK，只有 draft/CompletePlan 检验，无真实模型、无 Pulse。
- [测试报告](TEST_REPORT.md)、[架构](ARCHITECTURE.md)、[输入输出](AGENT_INPUT_OUTPUT.md)、[实现](IMPLEMENTATION.md)、[数据流](DATA_FLOW.md)、[限制](LIMITATIONS.md)。

本场景通过只证明单候选动作链路接线，不证明复杂规划、资源优化或两个真实 LLM 协作。本轮停止于 M3-A。

只读复核（不调用模型、不重新运行 Pulse）：

```bash
python -m core301.research_runtime.m3a_verify experiments/results/m3a_real_treatment_agent/m3a-real-agent-001
```

模型服务报告 usage 为 prompt=612、completion=66、total=678；费用未提供，记录 null。最终八阶段全部 PASS。
