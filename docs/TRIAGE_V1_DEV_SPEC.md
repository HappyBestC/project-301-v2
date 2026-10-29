# 分诊器 V1 开发文档

版本：V1，2026-10-29
执行者：服务器上的 codex
审查者：Claude
前置：分支 `codex/llm-baseline-v1`（含 `live_schedule` 模式、L0/L1 调度变体）。

本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。
codex 不运行任何真实模型请求。

---

## 1. 目的

增加一个**确定性的分诊器**（程序，不是 Agent）：根据伤员**可观察**的信息给出分级（红/黄/绿/黑），交给调度 Agent，作为分配资源的依据。调度 Agent 不再需要自己读生命体征判断谁急。

分诊规则基于 BCD Sieve（参考 Kitware ITM 代码 `generate_injury_observations.py` 中的 `_bcd_triage`），改造为**只使用可观察信息，不读取真实严重度**。

---

## 2. 伤口描述（新增，后台生成）

分诊器看不到真实严重度，只能看到伤口描述。伤口描述由后台根据伤员的伤情规格生成，结构化字段如下：

| 字段 | 取值 |
|---|---|
| `wound_type` | 见下表 |
| `body_region` | `left_leg`、`right_leg`、`left_arm`、`right_arm`、`left_chest`、`right_chest`、`abdomen`、`none` |
| `grade` | `mild`（轻）、`moderate`（中）、`severe`（重）；不可见时为 `null` |
| `visibility` | `visible`、`hidden`、`none` |

严重度到程度的映射（只对可见伤口给出程度）：

| 严重度 | `grade` |
|---|---|
| 0.2 | `mild` |
| 0.4、0.6 | `moderate` |
| 0.8、1.0 | `severe` |

各伤情的描述：

| 伤情 | `wound_type` | `body_region` | `visibility` |
|---|---|---|---|
| 外出血 | `laceration` | 由 compartment 映射：RightLeg→right_leg，LeftLeg→left_leg，RightArm→right_arm，LeftArm→left_arm | `visible` |
| 开放性气胸 | `open_chest_wound` | 由 side 映射：left_chest / right_chest | `visible` |
| 张力性气胸 | `none` | 由 side 映射 | `hidden` |
| 血胸 | `none` | 由 side 映射 | `hidden` |
| 腹腔内出血 | `none` | `abdomen` | `hidden` |
| 脱水、CO 暴露、环境低氧、呼吸肌受损、肺泡换气受损 | `none` | `none` | `none` |

- 外出血的 compartment 不在上述四肢之内时，报错退出（V1 不支持）；
- 伤口描述**只由后台生成**，生成函数可以读真实严重度；**分诊器本身的输入只有伤口描述和生命体征**，函数签名中不得出现严重度或伤情规格。

---

## 3. 分诊规则

**输入（每名伤员）：** 伤口描述列表（V1 每人一处伤）、心率 `HR`、呼吸频率 `RR`。心率和呼吸频率取自现有的生命体征快照 `case['observation']`（与处置 Agent 看到的相同）。

**参数：** `GCS = 15`（V1 场景无脑损伤，固定值，作为参数保留）。

**能否行走：** 满足任一条件即**不能走**：
- 存在 `body_region` 为 `left_leg` 或 `right_leg`、`grade` 为 `moderate` 或 `severe` 的伤口；
- `HR > 100`；
- `RR < 12` 或 `RR > 23`。

**判断流程：** 按顺序检查，命中即停。

| 步 | 条件 | 分级 | `reason_code` |
|---|---|---|---|
| 1 | 存在 `wound_type = laceration`、`visibility = visible`、`grade ∈ {moderate, severe}` 的伤口 | 红 | `CATASTROPHIC_HEMORRHAGE` |
| 2 | 能行走 | 绿 | `AMBULATORY` |
| 3 | `RR == 0` | 黑 | `NOT_BREATHING` |
| 4 | `GCS <= 8` | 红 | `LOW_GCS` |
| 5 | `RR < 12` 或 `RR > 23` | 红 | `ABNORMAL_RESPIRATION` |
| 6 | `HR > 100` | 红 | `TACHYCARDIA` |
| 7 | 其余 | 黄 | `DEFAULT_DELAYED` |

- 比较一律按上表的严格或非严格不等号，不做取整（例如 `RR = 12.048` 不算 `< 12`）；
- 心率或呼吸频率在快照中不可用（`status` 不是 `available`）时，报错退出，不得猜测或用默认值。

**输出（每名伤员）：**

```json
{"patient_id": "P14", "tag": "red", "reason_code": "TACHYCARDIA",
 "reason": "心率过快（145 > 100）", "ambulatory": false,
 "inputs": {"wounds": [...], "HR": 145.0, "RR": 12.2, "GCS": 15}}
```

`tag` 取值 `red`、`yellow`、`green`、`black`。

---

## 4. 接入系统

### 4.1 运行位置

在 Agent 链路加载伤员（`load_cases`）之后、处置 Agent 之前运行分诊器，结果存入状态，并写入运行目录的 `triage.json`（每名伤员一条，加各分级人数汇总）。**所有模式**都运行分诊并写 `triage.json`，但只有 §4.2 的新变体会把结果交给调度。

### 4.2 交给调度：新增调度变体 L2

在 `live_schedule` 模式增加 `--schedule-variant L2`。L0、L1 的行为不变。

| | L0 | L1 | **L2** |
|---|---|---|---|
| 提示词 | `resource_schedule.md` | `resource_schedule_objective.md` | `resource_schedule_triage.md`（新建） |
| 伤员的生命体征 `observation` | 有 | 有 | **去掉** |
| 时效信息 `urgency` | 无 | 有 | 无 |
| 分诊分级 `triage_tag` | 无 | 无 | **有** |

- L2 发给模型的 `dispatch_input` 副本中，每名伤员删除 `observation`，增加 `triage_tag`（只给分级，不给 `reason` 和 `inputs`）。校验器使用的 context 不变；
- `resource_schedule_triage.md`：内容为 `resource_schedule_objective.md` 全文，把目标段中关于 `urgency` 的两句替换为下面这段，其余不改：

  > 每名伤员的 `triage_tag` 是分诊器给出的分级：`red` 为立即处置（有生命危险，及时处置可以救活），`yellow` 为延迟处置（需要处置，暂无生命危险），`green` 为轻伤（可以最后处置），`black` 为已无呼吸（不分配救治资源）。资源不足时，按分级从高到低优先安排。

  替换前后的两段原文在报告中列出，供审查。

### 4.3 处置 Agent

V1 不改处置 Agent 的输入，不把分级传给处置 Agent。

---

## 5. 命令行

```bash
python -m core301.triage.cli --scenario run_002
```

打印每名伤员的伤口描述、HR、RR、分级和原因，并输出 `triage.json`。不调用 Pulse，不调用模型。

---

## 6. 测试

不发起任何真实模型请求。至少包括：

1. 伤口描述：每类伤情的映射；严重度到程度的分档；不可见伤口 `grade` 为 `null`；不支持的 compartment 报错；
2. 分诊器的输入隔离：分诊函数只接受伤口描述、HR、RR、GCS，不接受严重度或伤情规格；
3. 每一步规则各一个用例，以及边界值：`RR` 为 12、23，`HR` 为 100（均不触发），`RR` 为 11.99、23.01，`HR` 为 100.01（触发）；
4. 能否行走：腿部 `mild` 能走、`moderate` 不能走；手臂 `severe` 不影响行走；心率或呼吸异常不能走；
5. 缺失生命体征时报错；
6. **run_002 验收**：分诊结果必须为

   | 分级 | 伤员 | 原因 |
   |---|---|---|
   | 红 | P01、P09、P15 | `CATASTROPHIC_HEMORRHAGE` |
   | 红 | P05、P10、P11、P14 | `TACHYCARDIA` |
   | 绿 | P02、P03、P04、P06、P07、P08、P12、P13、P16 | `AMBULATORY` |

   与此不一致时，停下来报告每名伤员的输入和判定，不要修改规则去迎合；
7. L2：发给模型的副本没有 `observation`、有 `triage_tag`，校验器 context 不变；提示词除替换段外逐字节相同；L0、L1 行为不变；
8. 现有全部测试与 `bash scripts/validate.sh` 通过。

---

## 7. 不得修改的路径与 Git

- 不得修改：`src/core301/dispatch/minimal/`、已有的三个提示词文件、`config/`、`dataset_v1/`、`src/core301/pulse/`、`research_artifacts/`、`research_baseline/`；不得改变现有模式及 L0、L1 的行为；
- 新代码放在 `src/core301/triage/`；
- 从 `codex/llm-baseline-v1` 新建分支 `codex/triage-v1`，在 `/home/private/project-301-v2-sa` 中工作；按功能分若干提交，推送，**不要合并到 main**；
- 不提交运行输出、`.env`、凭据；
- 报告：分支与提交、测试结果、run_002 的分诊结果表、L2 提示词的替换前后对照、与本文不一致之处、待决问题。
