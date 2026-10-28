# Agent 链路 V1 开发文档

版本：V1，2026-10-28
执行者：服务器上的 codex
审查者：Claude（读 GitHub 上的分支做代码审查）

本文是实现规格。凡是本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。凡是按本文做不到的地方，同样停下来报告，不要用变通方案悄悄绕过。

---

## 0. 目标与范围

### 0.1 要打通的链路

```text
加载场景 → 处置 Agent → 调度 Agent → 校验 ─┬─ 通过 → 生成执行时间线 → Pulse 执行 → 结局评价 → 结束
                            ▲            │
                            └─ 有冲突且未超过轮数上限：带冲突反馈重排
```

一次运行：读入 `dataset_v1/run_001` 的 16 名伤员，处置 Agent 给出候选方案，调度 Agent 选方案并排程，校验器检查，通过后按排程把救助动作注入每名伤员各自的 Pulse 引擎，推进到第 120 分钟，算出每名伤员的结局。

### 0.2 V1 明确不做的事

- 不做 CP-SAT 调度（以后按 §5.3 的接口替换进来）；
- 不做调度 → 处置的反馈回路（只在图上预留）；
- 不做事件驱动的重新决策：只在第 0 分钟决策一次，16 名伤员（含第 10、20 分钟才出现的）一次排完；
- 不加阵地，不改 `dataset_v1`、`config/medical_resources_v1`；
- 不运行真实模型，除非用户另行明确要求（见 §9）。

### 0.3 已定的设计约定（不得更改）

| 约定 | 内容 |
|---|---|
| 时间 | 全局时钟单位为分钟，范围 [0, 120]，即调度用的时间。Pulse 时间与它的换算见 §6.2 |
| 仿真速度 | 离线、尽可能快地推进，不与现实时间同步；不得有 sleep、墙钟对齐、实时节拍 |
| Agent 思考 | Agent 决策期间仿真时钟冻结；LLM 调用的现实耗时不计入仿真时间 |
| 动作生效 | 救助动作在**操作结束时刻**注入 Pulse，不是开始时刻 |
| 资源权威 | `config/medical_resources_v1/` 是唯一资源规则；不得另造资源表 |
| 校验 | 排程必须通过现有 `dispatch/minimal/validation.py`，不得修改校验器 |
| 留痕 | 每次 LLM 调用保存请求、原始响应、模型标识、usage、prompt SHA；不自动重试，失败如实记录 |
| 死亡与引擎失败 | 伤员终末事件（IrreversibleState、CardiacArrest）与引擎推进失败分开统计 |

---

## 1. 依赖

- 新增 LangGraph。在服务器的包源上安装当前可用的稳定版本（应为 1.x），**固定精确版本号**，写进 `pyproject.toml` 的依赖和 `requirements.lock.txt`，连同它的传递依赖一起锁定。
- 只用 LangGraph 做编排（`StateGraph`、节点、条件边）。**不使用 LangChain 的模型封装**：所有 LLM 调用沿用现有 OpenAI SDK 的写法和留痕方式（参照 `agent/complete_provider.py`、`dispatch/minimal/api.py::request_agent_schedule`）。
- 若包源装不上 LangGraph，停下来报告，不要用手写状态机代替。

---

## 2. 代码位置

新建包 `src/core301/agent_chain/`：

| 文件 | 内容 |
|---|---|
| `state.py` | 图状态 `ChainState`（§3） |
| `graph.py` | `build_graph(providers, config) -> CompiledGraph`，只负责节点和边 |
| `nodes.py` | 各节点函数（§4） |
| `treatment.py` | 处置 Agent：输入构造、输出合同、确定性准入、Provider（§5.1–5.2） |
| `scheduling.py` | 调度 Provider 接口及实现（§5.3） |
| `timeline.py` | 排程 → 执行时间线（§6.1） |
| `bridge.py` | Pulse 执行桥（§6） |
| `outcomes.py` | 结局计算（§7） |
| `audit.py` | 运行目录、留痕、SHA 清单（§8） |
| `runner.py` | 命令行入口，`python -m core301.agent_chain.runner`（§9） |
| `prompts/treatment_candidates_v1.md` | 处置 Agent 的系统 prompt |

测试放在 `tests/agent_chain/`。

**不得修改**：`dispatch/minimal/` 下任何文件、`config/medical_resources_v1/`、`dataset_v1/`、`research_artifacts/`、`research_baseline/`、`pulse/` 下的现有模块。只允许导入和调用。若确实需要改，停下来报告。

---

## 3. 图状态 `ChainState`

用 `TypedDict`。字段：

| 字段 | 类型 | 写入节点 | 说明 |
|---|---|---|---|
| `run_id` | str | 入口 | |
| `run_dir` | str | 入口 | 运行目录 |
| `mode` | str | 入口 | `offline` / `native_replay` / `live`（§9） |
| `horizon_min` | float | 入口 | 固定 120.0 |
| `cases` | list | load_scenario | `api.load_cases()` 的结果，**去掉其中的 `candidate_plans`**（由处置 Agent 重新生成） |
| `resources`, `mapping` | dict | load_scenario | `api.load_config()` 的结果 |
| `treatment_decisions` | dict[patient_id → dict] | treatment | 每名伤员的原始决策和准入结果 |
| `excluded_patients` | dict[patient_id → reason] | treatment | 处置决策失败、被排除的伤员 |
| `dispatch_input` | dict | build_dispatch_input | `api.build_input(...)` 的结果 |
| `schedule_attempts` | list | schedule | 每轮的候选排程、校验摘要 |
| `feedback` | dict 或 None | validate | `feedback.build_feedback(...)` 的结果 |
| `previous_response` | str 或 None | schedule | 上一轮模型原文 |
| `accepted_schedule` | dict 或 None | validate | 通过校验的排程 |
| `validation` | dict | validate | 最新校验结果 |
| `timeline` | list | build_timeline | 执行时间线（§6.1） |
| `execution` | dict[patient_id → dict] | execute | 每名伤员的执行记录 |
| `outcomes` | dict | evaluate | 结局（§7） |
| `status` | str | 各节点 | 见 §4 末尾 |

状态里只放可 JSON 序列化的数据。

---

## 4. 节点与边

| 节点 | 类型 | 做什么 |
|---|---|---|
| `load_scenario` | 代码 | `load_config()`、`load_cases()`；校验 16 人齐全；去掉 `candidate_plans` |
| `treatment` | LLM / 模板 | 对每名伤员调用处置 Provider，经 §5.2 准入，生成候选方案 |
| `build_dispatch_input` | 代码 | 把准入通过的候选方案放回各伤员的 `candidate_plans`，被排除的伤员不进调度；调用 `api.build_input(resources, mapping, cases, horizon_min=120.0, observation_time_min=60.0)` |
| `schedule` | LLM / 回放 | 调用调度 Provider（§5.3），得到候选排程 |
| `validate` | 代码 | 用 `validation.validate_schedule(dispatch_input, candidate)` **独立重新校验一次**；若 Provider 自带的校验结果与之不一致，记为错误并停止。另需满足 `demonstration_only == true`（与 `request_agent_schedule` 的规则一致） |
| `build_timeline` | 代码 | §6.1 |
| `execute` | 代码 | §6 |
| `evaluate` | 代码 | §7 |

边：

```text
START → load_scenario → treatment → build_dispatch_input → schedule → validate
validate --(无冲突)--------------------------------------------→ build_timeline → execute → evaluate → END
validate --(有冲突 且 已用轮数 < max_schedule_attempts)----------→ schedule
validate --(有冲突 且 已用轮数 = max_schedule_attempts)----------→ END（status = schedule_failed）
```

- `max_schedule_attempts` 默认 3，与现有 `agent_run.run_agent` 一致。
- 回到 `schedule` 时，把 `feedback.build_feedback(...)` 的结果和上一轮模型原文传入，规则照搬 `agent_run.run_agent`（历史冲突、撤回记录等）。
- 第一版只接受**全员可排**或**仅有 `missing_parameters` 原因未排**的结果，判定规则照搬 `agent_run.run_agent` 中提前结束的条件；多轮中保留"已通过且排入人数最多"的候选，规则同样照搬。
- 在 `graph.py` 中以注释标出两个预留位置，**本版不实现**：`schedule → treatment`（候选方案都排不下时回到处置 Agent），`execute → treatment`（事件驱动的重新决策）。

`status` 取值：`running`、`treatment_failed`（全部伤员都被排除）、`schedule_failed`、`execution_partial`（有伤员执行失败或不被支持）、`completed`。

---

## 5. 两个 Agent

### 5.1 处置 Agent 的输入

每名伤员调用一次（16 次调用，可并发）。输入只包含：

- `patient_id`、`location`、`arrival_time_min`；
- `known_injury_context`：伤情类型和部位/侧别（`load_cases` 给出的，**不含 severity**）；
- `observation`：`load_cases` 给出的五项基础生命体征及单位、采样时间；
- `allowed_actions`：该伤情类型允许的动作，取自 `research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json` 中对应伤情的 `actions`；
- 每个允许动作的简要说明：只给 `config/medical_resources_v1/actions.json` 中的 `allowed_start`（可在哪类地点启动）和 `predecessor_actions`、`injury_predecessors`。**不给人员、库存、车辆等资源信息**（处置 Agent 不看资源，这是 V1 的设定）。

不得把 `raw/`、`evaluation_evidence/`、severity 或任何未来时刻的数据放进输入。

已知简化（V1 接受，写进 `manifest.json` 的 `known_simplifications`）：这些观测来自数据集生成时的 Pulse 采样（受伤后约 2 分钟），与 §6.2 执行桥中重新推演的引擎不是同一次仿真，且第 10、20 分钟出现的伤员也给的是这份观测。V2 改为事件驱动决策时，再改为从执行中的引擎实时读取。

### 5.2 处置 Agent 的输出合同与准入

模型输出严格 JSON（pydantic 严格模式、禁止多余字段、拒绝重复键）：

```json
{
  "schema_version": "301.treatment.candidates.v1",
  "patient_id": "P01",
  "decision_type": "propose_candidates",
  "candidate_plans": [
    {"actions": ["control_external_bleeding", "fluid_resuscitation"], "rationale": "..."},
    {"actions": ["control_external_bleeding", "transfusion"], "rationale": "..."}
  ],
  "reasoning_summary": "...",
  "refusal_reason": null
}
```

- `decision_type` 取 `propose_candidates` 或 `no_treatment_needed`。后者 `candidate_plans` 为空，`refusal_reason` 必填（用于轻伤员）。
- `candidate_plans` 为 1–2 个；每个方案的 `actions` 是动作类型的有序列表，长度 ≥1，不得重复。

确定性准入（全部由代码检查，任何一条不满足即该伤员准入失败）：

1. `patient_id` 与输入一致；
2. 每个动作都在该伤员的 `allowed_actions` 内；
3. 依赖：动作的 `predecessor_actions`，以及按伤情类型触发的 `injury_predecessors`，都必须在同一方案中更早出现；
4. 两个候选方案的动作序列不得相同。

准入通过后，由代码（不是模型）把每个方案转换成**与 `load_cases()` 输出中的候选方案完全相同结构**的对象（即模板经 `load_cases` 处理后的样子，参见 `runs/medical_resources_deepseek_001/dispatch_input.json` 中各伤员的 `candidate_plans`）：

- 方案级字段：`plan_id` = `{patient_id}-plan-{序号}`；`injury_type` = 该伤员的伤情类型；`status`：`TemplateTreatmentProvider` 沿用模板原值 `template_only_not_executed`，`LLMTreatmentProvider` 用 `agent_proposed_not_executed`；
- `action_id` = `{plan_id}-a{序号}`；
- `depends_on`：方案中前一个动作的 `action_id`（第一个为空）；
- `target` 与 `injury_association`：与 `api.load_cases` 中的处理完全一致（`target` 只含 `patient_id`，再按 `actions.json` 中的 `target_kind` 补 `side` 或 `compartment`；`injury_association` 为 `known_injury_context`）。由于不能修改 `api.py`，在 `treatment.py` 中实现同样的转换，由 §10 第 3、4 条测试保证一致；
- `fixed_protocol_ref`：`{"protocol_id": "{action_type}.phase1.1", "source": "src/core301/pulse/v2/protocol_book.py"}`；`resource_mapping_ref`：按模板中同类动作的取值；
- `eligibility_status`：固定为 `eligibility_pending`（与现有数据一致，因此排程必须为 `demonstration_only: true`）；
- `no_treatment_needed`：生成一个动作为空的候选方案。

准入失败或调用失败的伤员：记入 `excluded_patients` 及原因，不进入调度，不使用模板替补。

### 5.1–5.2 的三种 Provider

| Provider | 用途 |
|---|---|
| `LLMTreatmentProvider` | 真实模型。每名伤员最多 1 次调用，不重试；`max_tokens`、超时与现有 provider 同量级；留痕写入 `treatment/{patient_id}/` |
| `TemplateTreatmentProvider` | 基线：直接返回 `action_plan_templates.json` 中该伤员的预设方案，转成 §5.2 的输出格式后同样走准入。用于 `native_replay` 和测试 |
| `FakeTreatmentProvider` | 测试用，返回预先设定的 JSON（包括非法输出），用于测准入 |

### 5.3 调度 Agent

接口：

```python
class SchedulingProvider(Protocol):
    async def propose(self, dispatch_input: dict, *, feedback: dict | None,
                      previous_response: str | None, audit_dir: Path) -> dict:
        """返回 {'schedule': dict | None, 'raw_response': str | None, 'metadata': dict}"""
```

| Provider | 内容 |
|---|---|
| `LLMSchedulingProvider` | 内部调用现有 `LLMDispatchProvider().decide_resource_schedule(...)`（即 `api.request_agent_schedule`），参数与 `agent_run.run_agent` 一致 |
| `ReplaySchedulingProvider` | 返回一个给定的排程文件，默认 `runs/medical_resources_deepseek_001/schedule.json`。用于 `native_replay`，不调用模型 |
| `FakeSchedulingProvider` | 测试用 |

以后的 CP-SAT 求解器按同一接口实现，图不用改。

---

## 6. Pulse 执行桥

### 6.1 执行时间线

从通过校验的排程生成每名伤员的事件列表，按时间排序：

| 事件 | 时刻（全局分钟） | 来源 |
|---|---|---|
| `injury_onset` | 伤员的 `arrival_time_min` | V1 约定：伤员在出现的那一刻受伤（`run_001` 没有受伤地点） |
| `apply_action` | 该操作的 `end_min` | 仅 `mode == "start"` 的操作 |
| — | — | `mode == "continue"` 的操作、转运、周期照护：**不产生 Pulse 动作**，只记入时间线备查 |

每个 `apply_action` 记录：`patient_id`、`task_id`、`action_id`、`action_type`、`target`、`location`、`time_min`。

### 6.2 每名伤员的 Pulse

- 每名伤员一个独立的 Pulse 引擎，各自在独立进程中运行；全部伤员并行，进程数取 min(伤员数, CPU 核数)。
- 初始化：StandardMale 冻结患者和初始状态，按现有协议稳定 60 秒，然后施加伤情。施加伤情的时刻记为该伤员的受伤时刻，对应全局时间 `arrival_time_min`。换算：`pulse_injury_time_s = (全局分钟 − arrival_time_min) × 60`。
- 伤情参数取 `dataset_v1/run_001/patient_specs.json`，转换成 Pulse 动作时复用现有适配器：`pulse/v2/injury_adapter.py`、`pulse/v2/protocol_book.py`；暴露类伤情参照 `pulse/v2/exposure_session.py`，血胸参照 `pulse/v2/hemothorax_session.py`。**不得自行编写伤情参数。**
- 救助动作转换成 Pulse 动作时，按伤情类型选择参数来源，参数一律不改：

  | 伤情类型 | 参数来源 |
  |---|---|
  | `protocol_book.OPEN_INJURIES` 中的 7 类 | `pulse/v2/treatment_adapter.py` 和 `protocol_book.protocol_id(...)` 给出的固定协议（phase1.1） |
  | `hemothorax`（`control_hemothorax_bleeding`、`chest_tube`） | `runtime/v2_1/adapters.action_payload(kind, None)`，即 V2.1 复合伤运行时使用的固定参数 |
  | `carbon_monoxide_exposure`、`environmental_hypoxia`（`remove_from_exposure`） | 同上，`action_payload("remove_from_exposure", None)`，即 `exposure_session.environment_action(0, 0.21)` |

  暴露类伤情的"施加伤情"，就是按 `patient_specs.json` 中的 `environment_gases` 调用 `exposure_session.environment_action(...)` 改变环境。
  补液、输血按固定协议的速率和总量输注，由 Pulse 自行输完。
- 增加一项测试：对两种来源都能生成的动作（7 类开放伤情中的动作），两者给出的 Pulse 动作必须完全相同。若不相同，停下来报告。
- 在 `manifest.json` 的 `known_simplifications` 中注明：血胸的单伤研究档案状态为 `BLOCKED`（`protocol_book.SPECIALTY_DECISIONS`，原因是负残余和引流终点未解决），本版借用复合伤运行时的固定参数执行，P07、P16 的结果标记为 `exploratory`。
- 推进：用原生整段推进。先推进到下一个事件时刻并注入动作，在两个事件之间按 60 秒一段推进并采样。注入动作前后各采样一次。推进到全局第 120 分钟。
- 动作是否生效，以引擎**实际接受**为准（参照 `research_runtime/bridge.py` 中原生回执的判断方式），不能以动作构造成功为准。
- 伤员出现 IrreversibleState 或 CardiacArrest 后，记录时刻并停止推进；此后的推进失败不另算引擎失败。没有终末事件的推进失败，记为引擎失败。
- 若用上表的来源仍无法执行，**不要为此修改适配器，也不要静默跳过**，按下面两种情况处理并写明原因：
  - **伤情本身无法施加**：该伤员不进入仿真，标记 `INJURY_UNSUPPORTED`；
  - **伤情能施加，但某个动作无法执行**：该动作标记 `ACTION_UNSUPPORTED`、不注入，**伤员继续推进到窗口结束**（相当于这个动作没有发生），伤员整体标记 `treatment_incomplete`。

现有 `research_runtime/` 中的时序协议（180/181 秒候选时刻、480 秒终点）**不适用于本桥**。本桥只复用伤情和动作的参数转换，不经过那些时间准入。

### 6.3 每名伤员的执行记录

- 每 60 秒的采样：HR、MAP、SBP、SpO2、RR、CardiacOutput、BloodVolume（单位与 A 线探测一致）；
- 每个 `apply_action`：计划时刻、实际注入的 Pulse 时刻、是否被引擎接受；
- Pulse 事件及发生时刻；
- 终末事件、引擎失败、`INJURY_UNSUPPORTED`、`ACTION_UNSUPPORTED` 各自的记录；
- 现实耗时和速度比。

---

## 7. 结局评价

每名伤员，在其窗口 [受伤时刻, 全局第 120 分钟] 内：

- `observed_integral_CO_L`：从受伤到最后一个有效采样的梯形积分；
- `integral_CO_L`：完整窗口的积分，按下表确定：

  | 情况 | `integral_CO_L` | `window_status` |
  |---|---|---|
  | 推进到窗口结束 | 等于 `observed_integral_CO_L` | `complete` |
  | 出现终末事件（IrreversibleState / CardiacArrest） | 积分到终末时刻，之后按 0 计入到窗口结束 | `complete_terminal` |
  | 引擎推进失败，且没有终末事件 | `null`（之后的状态未知，**不补零、不外推**） | `incomplete_engine_failure` |
  | `INJURY_UNSUPPORTED` | `null`，`observed_integral_CO_L` 也为 `null` | `not_simulated` |

  `ACTION_UNSUPPORTED` 的伤员仍按前三行计算，另带 `treatment_incomplete: true`；
- `terminal_event` 及时刻、首次 HypovolemicShock 时刻；
- 窗口结束时的 MAP、BloodVolume（若已终止或失败则为空）；
- 注入的动作数、被接受的动作数、不支持的动作数；
- `engine_failure`、`injury_unsupported`、`treatment_incomplete`、`exploratory` 标志。

全体汇总：

- 计数：伤员总数，以及各 `window_status` 的人数、死亡人数、`treatment_incomplete` 人数、`exploratory` 人数；
- ∫CO 只在 `integral_CO_L` 不为 `null` 的伤员上计算：给出总和、均值、**参与计算的人数（即分母）**、被排除伤员的 ID 及原因。不对缺失值做任何填补；
- 另给一组只计"`complete` 或 `complete_terminal`、且不是 `treatment_incomplete`、不是 `exploratory`"伤员的同样统计，作为干净口径。

现有十四条锁定评价规则本版**不调用**。

---

## 8. 运行目录与留痕

运行目录：`experiments/results/agent_chain/{run_id}/`，已存在则拒绝运行。

```text
manifest.json            运行参数、模式、提交号、依赖版本、Provider 名称
state/{节点名}.json       每个节点结束时的状态快照
treatment/{patient_id}/  请求、原始响应、准入结果
schedule/attempt_{n}/    请求、原始响应、候选排程、校验结果、反馈
timeline.json
execution/{patient_id}/  samples.csv、events.json、actions.json
outcomes.json
summary.json
sha256_manifest.json
```

运行输出**不提交进 Git**：在 `.gitignore` 中加入 `/experiments/results/agent_chain/`。

---

## 9. 运行模式

| 模式 | 处置 | 调度 | Pulse | 模型调用 |
|---|---|---|---|---|
| `offline` | Fake | Fake | 假的 Pulse worker | 无 |
| `native_replay` | Template | Replay（DeepSeek 排程） | 真实 | 无 |
| `live` | LLM | LLM | 真实 | 有 |

入口：`python -m core301.agent_chain.runner --mode {offline|native_replay|live} --run-id ID [--max-schedule-attempts 3]`。

`live` 模式**只在用户另行明确要求时运行**。本次开发只运行 `offline` 和 `native_replay`。

---

## 10. 测试（`tests/agent_chain/`）

不得发起真实模型请求。至少覆盖：

1. 图的结构：节点、边、条件边的三种走向；
2. 处置准入：非法动作、依赖顺序错误、重复动作、两个方案相同、`patient_id` 不符、`no_treatment_needed` 缺理由，均被拒绝；合法输出转换后与模板结构一致；
3. `TemplateTreatmentProvider` 生成的候选方案，与 `api.load_cases()` 输出中的 `candidate_plans` 逐字段一致；
4. 用 Template + Replay 构造的 `dispatch_input`，与 `runs/medical_resources_deepseek_001/dispatch_input.json` 中的伤员和候选方案一致，回放排程通过校验、0 冲突；
5. 时间线：动作在 `end_min` 注入；`continue`、转运、照护不产生 Pulse 动作；时间换算正确（包括第 10、20 分钟出现的伤员）；
6. 调度重试：有冲突时回到 `schedule` 且带上反馈；达到上限后以 `schedule_failed` 结束；
7. 结局：∫CO 梯形积分；§7 表中四种 `window_status` 各自的积分规则；汇总的分母与被排除伤员列表；引擎失败与终末事件分开；
8. 代码中不存在按现实时间等待的逻辑（静态检查 `agent_chain/` 中无 `time.sleep`、无墙钟节拍）。

需要原生 Pulse 的测试加 `integration` 标记。

---

## 11. 验收

全部满足才算完成：

1. 全量非 integration 测试通过，原有 1252 个不受影响；integration 测试通过；
2. `bash scripts/validate.sh` 退出码为 0；`python scripts/verify_offline.py` 结果不变；
3. `offline` 模式跑通，`status == completed`；
4. `native_replay` 模式跑通：16 名伤员进入执行；报告每名伤员的结局表（受伤时刻、注入动作数／被接受数／不支持数、终末事件及时刻、`window_status`、∫CO、窗口结束时的 MAP 和 BloodVolume、各项标志）；所有 `INJURY_UNSUPPORTED`、`ACTION_UNSUPPORTED` 都写明原因；
5. 未修改 §2 列出的禁止修改的文件。

---

## 12. Git 与报告

- 从本文所在的提交新建分支 `codex/agent-chain-v1`；
- 按功能分成若干提交，提交信息写清楚做了什么；
- 推送到 GitHub，**不要合并到 main**；
- 不提交任何运行输出、`.env`、凭据。

报告内容：

1. 分支名和提交列表；
2. LangGraph 及新增依赖的精确版本；
3. 测试结果（通过、失败、跳过数）；`validate.sh` 和 `verify_offline.py` 的结果；
4. `offline`、`native_replay` 两次运行的 `summary.json`，以及 §11 第 4 条要求的结局表；
5. 与本文不一致的地方，逐条列出原因；
6. 待决问题：所有需要设计决定、本文未覆盖的事项。
