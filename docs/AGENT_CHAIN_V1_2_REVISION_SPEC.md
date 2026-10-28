# Agent 链路 V1.2 修订文档

版本：V1.2，2026-10-28
执行者：服务器上的 codex
审查者：Claude
前置：main 已包含 Agent 链路 V1 和阵地 V1.1。本文只描述相对 `docs/AGENT_CHAIN_V1_DEV_SPEC.md` 的修改，未提到的部分保持不变。

起因：`agent_chain_run_002_live_002`（DeepSeek）中，处置 Agent 有 3 人因输出被截断而失败；调度第 2 轮已得到 0 冲突、排入 8 人的方案，但因"必须全员排入"的规则被拒绝，最终没有一名伤员进入 Pulse。

本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。

---

## 1. 修改一：处置 Agent 的输出上限

- `LLMTreatmentProvider` 的 `max_tokens` 从固定 1200 改为参数，默认 **8192**；
- `runner` 增加 `--treatment-max-tokens`，默认 8192，取值范围 256–32768；
- 实际使用的值写入 `manifest.json` 的 `parameters`。

处置失败原因要能区分。在 `treatment/{patient_id}/admission.json` 和 `excluded_patients` 中使用以下原因码，替换现在笼统的 `TREATMENT_CALL_FAILED:RuntimeError`：

| 原因码 | 条件 |
|---|---|
| `OUTPUT_TRUNCATED` | `finish_reason == "length"`（无论正文是否为空） |
| `EMPTY_RESPONSE` | 正文为空，且不是上一条 |
| `CALL_FAILED` | 请求异常；附 `error_type`、`status_code` |
| `JSON_INVALID` | 正文不是合法 JSON |
| `ADMISSION_REJECTED` | JSON 合法，但不满足 §5.2 的准入规则；附原文 detail |

`finish_reason` 由 provider 如实记录，不得从正文推断。不改变"每人最多 1 次调用、不重试、不用模板替补"的规则。

调度 Agent 的请求参数（`api.request_agent_schedule`）不改。

---

## 2. 修改二：接受部分排程

替换原规格 §4 中的接受规则：

1. 某一轮校验 **0 冲突且全员排入**（或未排入者全部是 `missing_parameters`）：立即接受，结束重试（与原规则相同）；
2. 否则继续重试，直到达到 `max_schedule_attempts`；
3. 达到上限后：在所有 **0 冲突** 的轮次中，取排入人数最多的一轮接受；人数相同时取轮次最早的。这一轮中未排入的伤员，保留其 `patient_results` 中的 `reason_code`、`reason`、`considered_alternatives`；
4. 所有轮次都有冲突：没有可接受的排程（见 §3，所有伤员不治疗）。

不得修改校验器，不得放宽冲突判定。只改变"0 冲突但有人未排入"时是否执行。

---

## 3. 修改三：场景中的所有伤员都进入仿真

**原则：结局的分母始终是场景中的全部伤员。** 任何一个环节没给某个伤员安排治疗，他照样在 Pulse 中推演到第 120 分钟，计入结局。否则"把难救的伤员排除掉"会让结局看起来更好，方法之间无法公平比较。

### 3.1 图的走向

替换原规格 §4 中的两条结束边：

```text
treatment --(全部伤员处置失败)--------------------------------→ build_timeline
validate  --(达到轮数上限，且没有任何 0 冲突的轮次)--------------→ build_timeline
```

也就是说，处置或调度失败后不再直接结束，而是带着"没有治疗动作"进入执行和评价。其余边不变。

### 3.2 每名伤员的治疗状态

`build_timeline` 为场景中的每名伤员确定 `treatment_status`：

| `treatment_status` | 条件 | Pulse 中的处理 |
|---|---|---|
| `scheduled` | 在被接受的排程中有选中的方案 | 按排程注入动作 |
| `unscheduled` | 进入了调度，但被接受的排程把他列为未排入 | 不施加治疗 |
| `treatment_excluded` | 处置 Agent 失败，未进入调度 | 不施加治疗 |
| `no_schedule` | 进入了调度，但没有任何可接受的排程（§2 第 4 条） | 不施加治疗 |

`no_treatment_needed`（处置 Agent 判断无需治疗、选中空方案）属于 `scheduled`，动作数为 0。

时间线中每名伤员都有 `injury_onset` 事件；不施加治疗的伤员只有这一个事件。

注意：`treatment_excluded` 的伤员不在调度输入里，不占用任何资源。在 `manifest.json` 的 `known_simplifications` 中注明这一点。

### 3.3 结局

在原规格 §7 的每名伤员结局中增加：

- `treatment_status`；
- `unscheduled_reason_code`、`unscheduled_reason`（仅 `unscheduled`，原样复制排程中的内容）；
- `treatment_exclusion_reason`（仅 `treatment_excluded`，即 §1 的原因码及附带信息）。

汇总中增加：

- 各 `treatment_status` 的人数；
- 按 `treatment_status` 分组的 ∫CO：每组的总和、均值、分母、死亡人数、发生 HypovolemicShock 的人数。

原有两种口径（全部可用、干净口径）不变；**`treatment_status` 不是排除理由**，未得到治疗的伤员照常计入。

### 3.4 运行状态

`summary.json` 的 `status` 只反映流程是否走完：

| `status` | 含义 |
|---|---|
| `completed` | 走到 `evaluate`，且没有引擎失败、伤情不支持或治疗不完整 |
| `execution_partial` | 走到 `evaluate`，但有上述任一情况 |
| `aborted` | 流程中途异常退出，没有结局 |

另增加两个字段描述各阶段的结果：

| 字段 | 取值 |
|---|---|
| `treatment_stage` | `ok`（全部通过准入）/ `partial` / `failed`（全部失败） |
| `schedule_stage` | `full`（全员排入）/ `partial`（有人未排入）/ `failed`（没有可接受的排程）/ `skipped`（处置全部失败，未调用调度） |

`runner` 的退出码：走到 `evaluate` 为 0，`aborted` 为 1。

---

## 4. 测试

不发起真实模型请求。在现有测试基础上至少增加：

1. `max_tokens` 默认 8192、可通过参数修改，并实际传入请求；越界值被拒绝；
2. §1 的五种处置失败原因码，各有一个假 provider 用例；
3. 接受规则：(a) 第 1 轮全员排入即接受；(b) 三轮都 0 冲突但都有人未排入，接受排入最多的一轮；人数相同时取最早一轮；(c) 三轮都有冲突，`schedule_stage == "failed"`；
4. 图的走向：处置全部失败 → 不调用调度、进入执行，`schedule_stage == "skipped"`；调度失败 → 进入执行；
5. 时间线和执行：四种 `treatment_status` 的伤员都进入执行；不治疗的伤员没有 `apply_action`；
6. 结局：`treatment_status` 及原因字段正确；按状态分组的汇总正确；未治疗的伤员计入两种原有口径的分母；
7. `run_001` 的 `native_replay`、`offline` 行为与 V1.1 完全一致（全员排入，`treatment_status` 全部为 `scheduled`）。

---

## 5. 验收

1. 全量非 integration 和 integration 测试全部通过；`bash scripts/validate.sh` 退出码为 0；`python scripts/verify_offline.py` 结果不变；
2. `run_001` 的 `native_replay` 重新运行：16 人结局与 V1.1 验收运行逐人完全相同（新增字段除外）；
3. 用 `offline` 模式和假 provider 在 `run_001` 上构造一次"部分排程"运行（例如让调度只排入其中 12 人），报告 summary.json 和按 `treatment_status` 分组的汇总；
4. **不运行 live**。修订合并后由用户另行授权。

---

## 6. Git 与报告

- 从本文所在的提交新建分支 `codex/agent-chain-v1-2`；
- 按功能分成若干提交；推送到 GitHub，**不要合并到 main**；
- 不提交运行输出、`.env`、凭据。

报告内容：分支和提交列表；测试结果；`validate.sh`、`verify_offline.py` 结果；§5 第 2 条的逐人对比；§5 第 3 条的 summary 和分组汇总；与本文不一致的地方；待决问题。
