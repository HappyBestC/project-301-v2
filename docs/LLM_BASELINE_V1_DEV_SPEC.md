# LLM 直接排程对比实验 V1 开发文档

版本：V1，2026-10-29
执行者：服务器上的 codex
审查者：Claude
前置：分支 `codex/standard-answer-v1`（`14fbfb9`），含标准答案求解器、共享缺损算法 `core301.standard_answer.deficit`、反应表读取 `core301.standard_answer.tables`。
真实数据：`runs/curve_probe_001/tables/`（反应表，已完成）、`runs/standard_answer/sa_run002_oracle_G0/` 与 `..._G60/`（标准答案）。

本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。
**codex 不运行任何真实模型请求。** 真实运行由用户在授权后用 §6 的命令执行。

---

## 1. 目的

回答研究点一的问题：**在相同的场景、相同的候选方案、相同的资源约束下，让 LLM 直接排程，结局比标准答案差多少。**

只比较"调度"这一环：处置方案统一用 `run_002` 的模板方案（与标准答案相同），不调用处置 Agent 的模型。

---

## 2. 实验设计

| 组 | 提示词 | 额外信息 | 反馈 |
|---|---|---|---|
| **L0 现状** | 现有 `resource_schedule.md`（目标：尽量多排人） | 无 | 现有反馈 + §3.3 的编号提示 |
| **L1 公平** | 现有提示词 + §3.2 的目标说明 | 每名伤员的时效信息（§3.1） | 现有反馈 + §3.3 的编号提示 |

- 场景：`run_002`；规划期 120 分钟；
- 每次运行最多 3 轮排程请求（与 Agent 链路一致），接受规则沿用 V1.2：有 0 冲突全员排入则立即接受，否则取 0 冲突轮次中排入最多的一轮；都有冲突则无可接受排程，全员不治疗；
- 每组重复 5 次，共 10 次运行、至多 30 次模型请求；
- 被接受的排程送入 Pulse（native），全部 16 人推演到第 120 分钟。

L1 的信息与目标与标准答案求解器完全相同（`run_002` 中典型严重度即真实严重度），两者的差别只在"由谁来算"。

---

## 3. 实现

### 3.1 时效信息（仅 L1）

从反应表为每名伤员、每个候选方案生成一段时效信息，附在**发给模型的** `dispatch_input` 副本中每名伤员的 `urgency` 字段（校验器使用的 context 不加此字段）：

```json
"urgency": {
  "source": "Pulse reaction tables, typical severity of this injury type",
  "untreated": {"terminal_event_after_injury_min": 73.0, "co_deficit_L": 495.9},
  "plans": {
    "P01-plan-1": {"effective_after_injury_min": {"0": {"death": false, "co_deficit_L": 0.0},
                                                   "10": {...}, "20": {...}, "30": {...}, "45": {...},
                                                   "60": {...}, "90": {...}, "120": {...}}}
  }
}
```

- 取值用 `core301.standard_answer.tables` 的同一套读取与插值（`table-mode typical`），按该伤员窗口 `H_i` 截取；超过 `H_i` 的时刻不列出；
- `untreated.terminal_event_after_injury_min` 不死亡时为 `null`；
- 数值保留一位小数。

### 3.2 目标说明（仅 L1）

新建提示词文件 `src/core301/dispatch/prompts/resource_schedule_objective.md`，内容为现有 `resource_schedule.md` 全文，**仅**把第一段的目标句替换为下面这段，其余不改：

> 你的目标是在不违反已知硬约束的前提下，**首先使死亡人数最少，其次使全部伤员的 CO 缺损总和最小**。排入人数本身不是目标：资源不足时，优先保证会因延误而死亡的伤员。每名伤员的 `urgency` 给出了 Pulse 测得的时效信息：`effective_after_injury_min` 的键是"方案第一个动作的操作结束时刻减去受伤时刻"（分钟），值是该时刻生效时的死亡与否和 CO 缺损；`untreated` 是不处置的结局。你需要逐一交代所有输入患者的结果。不要求最优性证明；不能为提高覆盖率编造资源或不可执行安排。

不得修改 `resource_schedule.md` 本身。

### 3.3 编号提示（L0、L1 都用）

在 Agent 链路的反馈环节（`agent_chain`，**不改** `dispatch/minimal/feedback.py`），对 `UNKNOWN_RESOURCE`、`NOT_PERSONNEL`、`RESOURCE_LOCATION`、`EQUIPMENT_REQUIREMENT`、`SPACE_REQUIREMENT`、`STAFF_CAPABILITY_OR_COUNT` 冲突，在反馈中增加 `valid_resource_hints`：按冲突任务的地点，列出该地点真实存在的、类型或能力符合该动作要求的资源 ID。只列"存在且类型匹配"，不判断是否空闲，不替模型选择。

### 3.4 运行模式

在 `agent_chain.runner` 增加模式 `live_schedule`：处置用 `TemplateTreatmentProvider`（不调用模型），调度用 `LLMSchedulingProvider`；参数 `--schedule-variant {L0,L1}`、`--tables`（L1 必填）。`manifest.json` 记录组别、提示词 SHA-256、表的 SHA-256。

其余流程（校验、接受规则、时间线、Pulse 执行、结局）与现有 `live` 完全相同。

---

## 4. 评价

新增 `python -m core301.standard_answer.compare`（或等价位置），读取若干次运行目录和标准答案目录，输出：

1. **每次运行一行**：组别、被接受的轮次、排入人数、冲突数（每轮）、Pulse 死亡数、CO 缺损总和、模型 token 用量、模型耗时；
2. **每组汇总**：排程通过率（有可接受排程的运行占比）、死亡数与 CO 缺损的均值、最小、最大；
3. **对照**：不治疗（`live_003`）、标准答案 G0、G60 的同口径数值；
4. **逐人对比**：每名伤员在各运行中是否排入、第一个动作的生效延迟、是否死亡、CO 缺损，与标准答案并列；
5. 缺损一律用 `core301.standard_answer.deficit` 和健康参考 `runs/curve_probe_001/runs/reference_healthy` 计算，按 `H_i` 截取。没有可接受排程的运行按"全员不治疗"计入，不得剔除。

输出 `comparison.csv`、`per_patient.csv`、`summary.md`。

---

## 5. 测试

不发起任何真实模型请求。至少包括：

1. `live_schedule` 模式用假调度 provider 跑通，处置不调用模型；
2. 时效信息：与反应表逐项一致、按 `H_i` 截取、只进入发给模型的副本、L0 不含此字段；
3. 目标说明提示词：除目标句外与原文逐字节相同；
4. 编号提示：每种冲突码各一个用例，提示中的 ID 都真实存在且类型匹配；
5. 对比脚本：用构造的运行目录测试汇总、对照和"无可接受排程按全员不治疗计入"；
6. 现有全部测试与 `bash scripts/validate.sh` 通过。

---

## 6. 真实运行（用户执行）

codex 完成后，在报告中给出以下命令的最终形式，并说明预计模型请求数与耗时：

```bash
cd /home/private/project-301-v2-sa && source scripts/activate.sh
for i in 1 2 3 4 5; do
  python -m core301.agent_chain.runner --mode live_schedule --schedule-variant L0 --scenario run_002 --run-id llm_L0_$i
  python -m core301.agent_chain.runner --mode live_schedule --schedule-variant L1 --scenario run_002 \
      --tables runs/curve_probe_001/tables --run-id llm_L1_$i
done
python -m core301.standard_answer.compare --runs 'llm_L*' --standard runs/standard_answer/sa_run002_oracle_G0 \
    runs/standard_answer/sa_run002_oracle_G60 --out runs/llm_baseline_v1
```

---

## 7. 不得修改的路径与 Git

- 不得修改：`src/core301/dispatch/minimal/`、`src/core301/dispatch/prompts/resource_schedule.md`、`config/`、`dataset_v1/`、`src/core301/pulse/`、`research_artifacts/`、`research_baseline/`；不得改变现有 `offline`、`native_replay`、`live` 模式的行为；
- 从 `codex/standard-answer-v1` 新建分支 `codex/llm-baseline-v1`，在 `/home/private/project-301-v2-sa` 中工作；按功能分若干提交，推送，**不要合并到 main**；
- 不提交运行输出、`.env`、凭据；
- 报告：分支与提交、测试结果、§6 的最终命令与预计请求数、与本文不一致之处、待决问题。
