# 标准答案求解器（CP-SAT）V1 开发文档

版本：V1，2026-10-28
执行者：服务器上的 codex
审查者：Claude
前置：main 已包含 Agent 链路 V1.2；反应表测量脚本 `scripts/curve_probe.py` 已随本文提交，测量结果在服务器 `runs/curve_probe_001/`（不入库）。

本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。

---

## 1. 目的

对一个场景（伤员 + 资源配置），在**与现有校验器完全相同的资源约束**下，求出结局最好的排程，称为"标准答案"。它是衡量其他排程方法（LLM 排程、简单规则等）的尺子。

- 排程的好坏由**反应表**评估：每类伤员"方案的第一个动作在受伤后第 d 分钟生效"时的结局，由 `curve_probe.py` 用 Pulse 离线测出；
- 目标为**字典序**：先使死亡人数最少，在此前提下使心输出量缺损（CO 缺损）总和最小；
- 标准答案必须 (1) 通过现有校验器，冲突数为 0；(2) 送入 Pulse 实际推演后，结局与反应表的预测一致。

本阶段**不调用任何模型**，不修改 Agent 链路的行为。

---

## 2. 范围与简化（已与用户确认）

| 项 | V1 约定 |
|---|---|
| 场景 | `run_002`（`config/medical_resources_v1_1` + `dataset_v1/run_002`），并支持只改严重度的变体场景（§8） |
| 规划期 | 全局第 0–120 分钟，整分钟离散 |
| 候选方案 | 每名伤员的全部候选方案（`api.load_cases` 给出的 `candidate_plans`），每人至多选一个，或不排入 |
| **转运** | **每名伤员至多转运一次**，从受伤地点直接送到能完成整个方案的地点（A、B、H1、H2 之一）。不做两段转运 |
| 处置地点 | 方案的所有操作在目的地完成；但 `allowed_start` 含救护车类型的动作（`control_external_bleeding`、`occlusive_dressing`、`supplemental_oxygen`）也可以在转运途中、以车辆 ID 为地点进行 |
| 操作模式 | 只用 `mode = "start"`，不生成 `continue` 操作 |
| 静脉通路 | 一律 `access_mode = "new"`（每个方案至多一个需要通路的动作） |
| `demonstration_only` | 必须为 `true`（所有方案均为 `eligibility_pending`） |

阵地 F1、F2 没有任何资源，也不允许开始处置，所以未转运的伤员一定未得到治疗。

---

## 3. 输入

### 3.1 场景

复用现有代码，不自行解析：

```python
resources, mapping = api.load_config(paths['config_dir'])
cases = api.load_cases(paths['dataset_dir'])
context = api.build_input(resources, mapping, cases, horizon_min=120.0)
```

每个动作的时长、人员角色、耗材、设备、空间、前置动作、持续性、护理要求，**一律通过 `api.requirement(mapping, action, access_mode='new', mode='start')` 取得**，不得另写一份。

### 3.2 反应表

位于 `<tables_dir>`（默认 `runs/curve_probe_001/tables/`），格式由 `scripts/curve_probe.py` 的 `summarize` 定义。每张表对应一个（伤情组，方案）：

- `<group_id>__<plan_key>.csv`：每行一个处置时刻，列见脚本的 `FIELDS`。关键列：`d`（整数或 `untreated`）、`source`、`window_status`、`terminal_min`、`deficit_L_120`；
- `<group_id>__<plan_key>__cum_deficit_L.csv`：每行一个 `d`，列 `m0 … m120` 为受伤后逐分钟的累计 CO 缺损（升）；
- `group_id` 例：`external_hemorrhage_RightLeg__s0.4`、`carbon_monoxide_exposure__co0.005`、`environmental_hypoxia__o20.12`；
- `plan_key` 为方案动作类型按顺序用 `+` 连接，例：`control_external_bleeding+fluid_resuscitation`；
- `d` 的含义：**方案第一个操作的结束时刻（生效时刻）减去受伤时刻**，单位分钟；后续动作在测量时按"前一个结束即开始"安排（目录名中的 `@0,5` 即各动作相对第一个动作的生效偏移）。

伤员到表的映射：由伤员的伤情类型、部位（`compartment`/`side`）、严重度（或环境气体浓度）确定 `group_id`；由所选方案的动作序列确定 `plan_key`。找不到对应的表时报错退出，不得用其他表代替。

### 3.3 由表得到每名伤员的代价

伤员 i 受伤时刻为 `t_i`，观察窗口 `H_i = 120 − t_i`。对所选方案 p、第一个操作结束于全局时刻 `e`，令 `d = e − t_i`：

- **CO 缺损** `D_i(d)`：取 `cum_deficit` 表中第 `d` 行、第 `m{H_i}` 列；
- **死亡** `X_i(d)`：该行 `terminal_min` 非空且 `≤ H_i`；
- **未排入**：取 `d = untreated` 行，同样按 `H_i` 截取。

表中只有部分 `d` 被测量（5 分钟网格，转换处补到 1 分钟）。对未测量的 `d`：

- `D_i(d)`：在相邻两个已测量点之间线性插值（两个点各自先按 `H_i` 截取，再插值）；
- `X_i(d)`：取**不早于** d 的最近已测量点的值（死亡随延迟单调恶化时，这是保守的取法）；
- 表中存在死亡由"是"变"否"（d 增大时）的不单调处时，**照常使用并在报告中列出**，不得平滑。

预处理成每名伤员、每个方案、`e ∈ [t_i, 120]` 上的两个整数数组：`death[e] ∈ {0,1}`，`deficit10[e] = round(10 × D)`（精度 0.1 L）。`window_status` 不是 `complete`/`complete_terminal`、或 `source` 为 `error` 的行视为缺失。

---

## 4. 约束

**原则：`validate_schedule` 检查的每一条 conflict 规则，模型中都要有对应约束。** 下面按校验器的检查顺序列出 V1 涉及的规则；若发现遗漏，补上并写进报告。`unchecked` 类（如 `ELIGIBILITY_PENDING`、`STOP_CONDITION_UNCHECKED`）不是冲突，不需要建模。

### 4.1 转运（`transports`）

每名伤员至多一个转运任务，决策：车辆 `v`、目的地 `h ∈ {A,B,H1,H2}`、出发时刻 `s`。

- 车辆按时间顺序执行自己的转运；第一趟从 `vehicles[v].location` 出发，之后每趟从上一趟的 `destination` 出发（`VEHICLE_POSITION`）；
- 时刻完全由公式决定（`TRANSPORT_TIMING`）：
  `load_start = s + travel[出发地][pickup]`，`depart = load_start + loading`，`arrive = depart + travel[pickup][h]`，`handoff_end = arrive + handoff`，`end = handoff_end + turnaround`；
- 同一车辆相邻两趟：后一趟 `s ≥` 前一趟 `end`（`VEHICLE_OVERLAP`）；`end ≤ 120`（`OUTSIDE_HORIZON`）；`s ≥ t_i`（`BEFORE_ARRIVAL`）；
- 车辆人员在 `[s, end)` 被占用；担架在 `[load_start, handoff_end)` 被占用；
- 伤员位置：`[load_start, handoff_end)` 在车上（地点 = 车辆 ID），`handoff_end` 之后在 `h`。

建议建模方式（不强制）：每个（伤员，车辆，目的地）一个可选的"转运选项"，每辆车用 `AddCircuit` 对其选项排序，弧上的行驶时间由前一选项的目的地和后一选项的 pickup 决定。

### 4.2 操作（`operations`）

对所选方案的每个动作，生成恰好一个 `mode="start"` 操作（`PLAN_ACTION_MISSING`、`DUPLICATE_ACTION`），决策：地点、开始时刻、人员、设备、空间。

- **地点**：伤员在操作整个期间都在该地点（`PATIENT_LOCATION`）。即目的地 `h`（`start ≥ handoff_end`），或对 §2 所列动作为车辆 ID（`[start, end) ⊆ [load_start, handoff_end)`）。地点类型须在 `allowed_start` 内（`LOCATION_UNSUPPORTED`）；
- **时长**：`end − start = requirement(...)['duration_min']`（`ACTION_DURATION`）；`start ≥ t_i`，`end ≤ 120`；
- **前置**：方案内 `depends_on` 的动作须已结束；`predecessor_actions` 和 `injury_predecessors` 规定的动作类型须在同一方案内已结束（`DEPENDENCY_UNMET`）；
- **人员**：`staff_roles` 由不同人员覆盖，每人具备对应能力，且 `location` 等于操作地点（`STAFF_CAPABILITY_OR_COUNT`、`RESOURCE_LOCATION`）。有单独通路阶段的动作（输血），通路人员占用 `[start, start + access_phase)`，主操作人员占用 `[start + access_phase, end)`；
- **设备**：类型与 `equipment` 完全一致，位于操作地点。持续性动作（`continuous`）占用到第 120 分钟；否则占用到 `end + equipment_turnaround_min`；
- **空间**：类型在 `space_types[地点类型]` 内（车上为 `stretcher`）。持续性动作若不指定 `support_space_id`，空间占用到第 120 分钟；若指定，主空间只占用操作期间，`support_space_id`（类型在 `support_space_types` 内）从 `end` 占用到 120。胸管插入在 `treatment` 空间时**必须**指定支持空间（`SUPPORT_SPACE_REQUIRED`）。同一伤员不能同时占用两个床位（`DOUBLE_POSITION`，转运担架除外）。同一伤员相邻两个操作用同一空间时，中间的空档也算占用；
- **研究止血能力**：`space_capability` 为 `research_hemostasis` 的动作，操作期间占用所在医院唯一的该能力（`RESEARCH_CAPACITY`）；
- **耗材**：`consumables` 与规则（含新通路耗材）完全一致；
- **护理**（`care`）：持续性动作结束后，按 `care.period_min` 周期生成护理时段 `[end + k·period, end + k·period + duration)`，只生成整段落在 120 以内的时段。每个时段的地点是伤员当时所在的地点（例如车上开始的吸氧，送达后的护理在目的地），指派一名位于该地点、具备 `care.role` 能力的人员（`CARE_TIMING`、`CARE_MISSING`、`PATIENT_LOCATION`）。

### 4.3 资源互斥（`RESOURCE_OVERLAP`）

人员、设备、空间、车辆、研究止血能力：所有占用区间两两不重叠（半开区间）。例外与校验器一致：同一伤员的同一空间不重复计；车辆人员在本趟转运期间可为本趟伤员做车上操作或护理（`personnel_overlap_exempt`）。

### 4.4 库存（`STOCK_SHORTAGE`）

按地点（含车辆 ID）扣减，不跨地点借用：

- 件数耗材：每个操作扣 `consumables` 中的数量；
- `saline`、`blood`：每个补液、输血开始即承诺 `reservation_quantity`（500 mL），按地点累计不得超过库存；
- `oxygen`：`supplemental_oxygen` 按 `rate × (120 − end)` 扣减；`mechanical_ventilation` 的氧气在本实验范围外，不扣减（与校验器一致）。

### 4.5 未排入的伤员

`patient_results` 每人恰好一条。未排入者：`status = "unscheduled"`，`reason_code = "resource_shortage"`，`blocking_resources` 填车辆 ID 等实际为瓶颈的资源 ID，`reason` 用中文写明"在最优排程中资源分配给了其他伤员"（不少于 12 个字），`considered_alternatives` 列出考虑过的方案 ID。须满足 `check_results` 的全部规则。

---

## 5. 目标与求解

### 5.1 字典序两阶段

- 阶段一：最小化 `Σ death_i`；
- 阶段二：添加约束 `Σ death_i ≤ 阶段一的最优值`，最小化 `Σ deficit10_i`。

阶段一的状态必须是 `OPTIMAL`，才能说阶段二固定的是最优死亡数；若只是 `FEASIBLE`，照常进入阶段二，但在结果中标记 `deaths_optimality_proven = false`。阶段二同样记录状态和最优性间隙。

代价的取法：对每名伤员每个方案，用 `AddElement(e − t_i, death_table, death_var)` 和 `AddElement(e − t_i, deficit_table, deficit_var)` 查表；伤员的代价 = 所选方案的查表值，未排入时取 untreated 值。

### 5.2 后续动作的时序

反应表测量时，后续动作紧跟前一个动作执行。参数 `--max-followup-gap G`（分钟）约束：后续动作的生效时刻 `≤` 第一个动作的生效时刻 + 模板偏移 + G。

- `G = 0`：严格按模板时序，排程与反应表完全对应；
- G 的默认值**待用户根据 gapcheck 结果确定**，实现时默认 0，并在结果中记录。

### 5.3 求解参数

参数：`--time-limit-s`（默认 600，每阶段）、`--workers`（默认 8）、`--seed`（默认 0）。全部写入结果。OR-Tools 版本在 `pyproject.toml` 和锁文件中固定。

### 5.4 两种表模式

`--table-mode`：

- `oracle`（默认）：每名伤员用其**真实严重度**的表。得到的是标准答案；
- `typical`：每名伤员用其伤情类型的**典型严重度**的表，典型严重度取 `run_002` 中该伤情的严重度（环境暴露取 run_002 的浓度）。这是"只知道伤情类型"的方法，用于和标准答案比较。

两种模式的排程都按**真实严重度**评价（§6）。

---

## 6. 输出与复核

输出目录：`runs/standard_answer/<run_id>/`（不入库）。

1. `schedule.json`：`301.resource_schedule.v1` 格式的排程；
2. `validation.json`：`validate_schedule(context, schedule)` 的完整输出。**冲突数必须为 0**，否则视为求解器错误，报告中写明哪条规则未建模；
3. `prediction.json`：每名伤员按真实严重度的表预测的死亡、死亡时刻、CO 缺损，以及汇总；
4. `pulse/`：用 `agent_chain.timeline.build_timeline` 由排程生成时间线，用 `agent_chain.bridge.execute_all(native=True)` 推演全部伤员，再计算每人的死亡和 CO 缺损（缺损的算法与 `curve_probe.py` 的 `minute_values` + `cumulative_deficit` 完全相同，参考轨迹用 `runs/curve_probe_001/runs/reference_healthy`）；
5. `comparison.json`：逐人对比预测与 Pulse 实测。一致的判据：死亡与否相同；死亡时刻相差 ≤ 1 分钟；CO 缺损相差 ≤ max(2 L, 2%)。不一致的伤员逐一列出，并说明可能的原因（插值、后续动作时序偏离模板等）；
6. `solve.json`：两阶段的状态、目标值、界、求解时间、参数、OR-Tools 版本、表的版本（`tables_dir` 下各文件的 SHA-256）。

把计算 CO 缺损的函数从 `scripts/curve_probe.py` 移到共享模块（例如 `src/core301/standard_answer/deficit.py`），脚本改为导入它；**不得改变计算结果**，用 `curve_probe_001` 的现有输出做回归测试。

---

## 7. 代码结构与命令

新建包 `src/core301/standard_answer/`，建议模块：`tables.py`（读表、映射、插值）、`model.py`（建模）、`solve.py`（两阶段求解）、`export.py`（生成排程 JSON）、`verify.py`（校验与 Pulse 复核）、`cli.py`。

```bash
python -m core301.standard_answer.cli solve  --scenario run_002 --tables runs/curve_probe_001/tables \
    --table-mode oracle --run-id sa_run002_oracle_001
python -m core301.standard_answer.cli verify --run-id sa_run002_oracle_001
```

`solve` 不调用 Pulse；`verify` 调用 Pulse，不调用模型。

---

## 8. 变体场景

支持"伤员组成、受伤时刻、地点、资源都与 run_002 相同，只改部分伤员的严重度或环境浓度"的场景：

- 输入：一个 JSON 文件，例如 `{"base": "run_002", "overrides": {"P01": {"severity": 0.8}, "P09": {"severity": 0.6}}}`；
- 只用于 `solve` 和 `verify`，不生成 Agent 链路所需的观测文件，不写入 `dataset_v1/`；
- 改动后的伤员若没有对应的反应表，报错退出。

---

## 9. 测试

不发起任何模型请求。至少包括：

1. **表**：读取、伤员到表的映射、按 `H_i` 截取、插值（含死亡的保守取法）、缺失行的处理；用手工构造的小表测试；
2. **约束覆盖**：对每一条 §4 的规则，构造一个违反它的排程，确认校验器报冲突，且模型不会产生这种排程；
3. **小场景最优性**：构造 3–4 名伤员、1 辆车、目的地资源充足的场景，穷举"车辆服务顺序 × 方案选择"，每种按最早可行时刻排程，取最优；与 CP-SAT 结果的目标值一致；
4. **端到端（不调用 Pulse）**：在 run_002 上用假反应表求解，得到的排程通过校验器、冲突为 0；
5. 现有全部测试和 `bash scripts/validate.sh` 仍然通过。

---

## 10. 验收

1. 测试全部通过；
2. 在 `runs/curve_probe_001` 的真实反应表上（至少 run_002 原有严重度的表已完成）：
   - `solve --table-mode oracle`：两阶段状态、死亡数、CO 缺损、求解时间；排程冲突数为 0；
   - `verify`：逐人对比结果；
3. 报告给出标准答案与 `agent_chain_run_002_live_003`（不治疗，3 人死亡）的对比；
4. 不运行任何 live 模型调用。

---

## 11. 不得修改的路径

`src/core301/dispatch/minimal/`、`config/`、`dataset_v1/`、`src/core301/pulse/`、`research_artifacts/`、`research_baseline/`（OR-Tools 依赖引起的锁文件更新除外，须在报告中说明）。不得修改 Agent 链路的现有行为。

## 12. Git 与报告

- 分支 `codex/standard-answer-v1`，按功能分若干提交，推送到 GitHub，**不要合并到 main**；
- 不提交运行输出、`.env`、凭据；
- 报告内容：分支和提交列表；测试结果；§10 的各项结果；未建模或与本文不一致的地方；待决问题。
