# 阵地资源模型 V1.1 开发文档

版本：V1.1，2026-10-28
执行者：服务器上的 codex
审查者：Claude
前置：main 已包含 Agent 链路 V1（`docs/AGENT_CHAIN_V1_DEV_SPEC.md`）

本文是实现规格。本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。按本文做不到的地方，同样停下来报告，不要用变通方案绕过。

---

## 0. 目标与范围

### 0.1 要做的事

1. **新资源配置 V1.1**：在现有资源模型上加两个阵地 F1、F2，以及它们到各节点的路程；
2. **新场景 `run_002`**：16 名伤员改为在阵地受伤，等车接走；
3. **Agent 链路支持选择场景**：`run_001` 和 `run_002` 都能跑；
4. **修复脱水伤员无法仿真**：脱水在 Pulse 里是初始化条件，要在引擎初始化时设定（V1 中 P08 被标为 `INJURY_UNSUPPORTED`）。

### 0.2 不做的事

- **不改 V1 的配置和数据**：`config/medical_resources_v1/`、`dataset_v1/run_001/` 原样保留。`run_001` 和 DeepSeek 基线快照要继续可复现，`verify_offline.py` 结果不得变化；
- 不改 `dispatch/minimal/`、`research_artifacts/`、`research_baseline/`、`src/core301/pulse/` 下的任何文件；
- 不做 `run_002` 的端到端排程运行（目前没有不调用模型的排程器，见 §6 末尾）；
- 不运行真实模型。

### 0.3 已定的设计（不得更改）

| 事项 | 内容 |
|---|---|
| 阵地 | 两个：F1、F2，节点类型 `field` |
| 阵地上的资源 | 没有人员、设备、空间、库存 |
| 阵地上的处置 | 不允许。现有 12 个动作的 `allowed_start` 都不含 `field`，校验器会自动拒绝，**不要修改 `actions.json`** |
| 伤员受伤 | 在阵地受伤，`arrival_time_min` 表示受伤时刻；Pulse 从受伤时刻开始推演，等车、转运期间伤情持续演变 |
| 车上处置 | 保持现有规则（外出血控制、封闭敷料、给氧可在救护车上启动；针刺减压不行） |

---

## 1. 资源配置 V1.1

新建目录 `config/medical_resources_v1_1/`：

| 文件 | 内容 |
|---|---|
| `actions.json` | 从 `config/medical_resources_v1/actions.json` **逐字节复制**，不做任何修改 |
| `resources.json` | 从 V1 复制后，只做下面列出的改动 |

`resources.json` 的改动，**只有这四处**：

1. `version` 改为 `301.medical_resources.v1.1`；
2. `nodes` 增加：
   ```json
   "F1": {"type": "field"},
   "F2": {"type": "field"}
   ```
3. `travel_min` 补全为 6 × 6 的完整矩阵。原有 A、B、H1、H2 之间的路程**一个都不改**，新增的路程如下（单位：分钟，双向相同，自己到自己为 0）：

   |  | A | B | H1 | H2 | F1 | F2 |
   |---|---:|---:|---:|---:|---:|---:|
   | **F1** | 8 | 18 | 18 | 28 | 0 | 20 |
   | **F2** | 16 | 8 | 26 | 16 | 20 | 0 |

   完整矩阵中，A、B、H1、H2 各行也要补上到 F1、F2 的值（与上表对称）。
4. `notes` 末尾追加一条：`"Field nodes F1/F2 (V1.1): casualty locations only; no personnel, equipment, spaces or inventory; no treatment can start there."`

`source_sha256` 保持原样：它指向的 `my-docs/` 下两份规则文档和 `config/medical_resources_v1/experiment_parameters_v1.json` 都没有变化，`api.load_config(directory)` 的 SHA 校验应照常通过。

---

## 2. 场景 `run_002`

新建目录 `dataset_v1/run_002/`。伤员、伤情、受伤时刻都和 `run_001` 相同，**只改受伤地点**：`run_001` 中在 A 的伤员改到 F1，在 B 的改到 F2。

| 伤员 | 伤情 | 受伤地点 | 受伤时刻（分钟） |
|---|---|---|---:|
| P01–P04 | 外出血、腹腔内出血、呼吸肌受损、CO 暴露 | F1 | 0 |
| P05–P08 | 张力性气胸、腹腔内出血、血胸、脱水 | F2 | 0 |
| P09、P10 | 外出血、开放性气胸 | F1 | 10 |
| P11、P12 | 张力性气胸、肺泡气体交换受损 | F2 | 10 |
| P13、P14 | 呼吸肌受损、环境低氧 | F1 | 20 |
| P15、P16 | 外出血、血胸 | F2 | 20 |

以 `run_001` 中的实际值为准，按"A → F1、B → F2"替换；上表只是方便核对。

目录内容：

| 文件 | 做法 |
|---|---|
| `patient_specs.json` | 从 `run_001` 复制，只把 `location_id` 按上述规则替换，其余字段不变 |
| `patients_initial.json` | 从 `run_001` 复制，只把 `location_id` 按同样规则替换 |
| `action_plan_templates.json` | 从 `run_001` **逐字节复制** |
| `patient_observations/` | 从 `run_001` **逐字节复制** 16 个文件 |
| `README.md` | 说明：由 `run_001` 派生；仅受伤地点不同；观测沿用 `run_001` 的 Pulse 采样（受伤后约 2 分钟），与执行桥重新推演的引擎不是同一次仿真（V1 已知简化，沿用） |

`raw/`、`evaluation_evidence/` 等其他文件不复制。

---

## 3. Agent 链路支持选择场景

在 `src/core301/agent_chain/` 中增加场景注册表：

```python
SCENARIOS = {
    'run_001': {'config_dir': 'config/medical_resources_v1', 'dataset_dir': 'dataset_v1/run_001',
                'replay_schedule': 'runs/medical_resources_deepseek_001/schedule.json'},
    'run_002': {'config_dir': 'config/medical_resources_v1_1', 'dataset_dir': 'dataset_v1/run_002',
                'replay_schedule': None},
}
```

把场景一路传下去，替换现在写死 `run_001` 的地方：

| 位置 | 现状 | 改为 |
|---|---|---|
| `nodes.load_scenario` | `api.load_config()`、`api.load_cases()` | `api.load_config(config_dir)`、`api.load_cases(dataset_dir)` |
| `treatment.template_decisions`、`admit` 中读模板 | `api.DATASET` | 场景的 `dataset_dir` |
| `bridge.execute_all` 读 `patient_specs.json` | `api.DATASET` | 场景的 `dataset_dir` |
| `scheduling.ReplaySchedulingProvider` | 固定 DeepSeek 排程 | 场景的 `replay_schedule` |
| `runner` | 无场景参数 | 增加 `--scenario {run_001,run_002}`，默认 `run_001` |
| `manifest.json` | — | 记录场景名、`config_dir`、`dataset_dir`，以及这些目录下各文件的 SHA |

`ChainState` 增加 `scenario` 字段。

规则：

- `run_002` 没有回放排程，因此 `native_replay` 和 `offline` 模式在 `run_002` 上要**直接拒绝并给出明确错误**，不要退回 `run_001` 的排程；
- `api.load_cases` 读目标规则时用的是 V1 的 `actions.json`（写死在 `api.py` 里，不能改）。由于 V1.1 的 `actions.json` 与 V1 逐字节相同，结果一致。用 §5 的测试保证这一点。

---

## 4. 脱水伤员在初始化时设定

伤情类型 `dehydration` 改为在引擎初始化时设定：

- 用现有的 `pulse/v2/injury_adapter.PatientInitializer().configuration(casualty)` 生成患者配置，`casualty` 按该伤员的 `patient_specs.json` 构造；
- 用 `ResearchPulseSession.initialize(log_path, configuration=...)` 初始化引擎，**代替**从冻结状态恢复；
- 之后照常稳定 60 秒；稳定结束的时刻即为该伤员的受伤时刻，不再提交动态伤情动作；
- 在 `manifest.json` 的 `known_simplifications` 中注明：脱水作为初始化条件，从引擎启动时就存在（包括 60 秒稳定期），与其他伤情"稳定后施加"的时序不同。

只在 `agent_chain/bridge.py` 中改调用方式，**不修改适配器和 session**。如果现有的 `PatientInitializer` 或 `initialize(configuration=...)` 不能直接用，停下来报告。

其他伤情类型的处理不变。

---

## 5. 测试（`tests/agent_chain/` 或新建 `tests/field_nodes/`）

不发起真实模型请求。至少覆盖：

**配置**
1. V1.1 的 `actions.json` 与 V1 逐字节相同；
2. V1.1 的 `resources.json` 与 V1 相比，只有 §1 列出的四处不同（用结构化比较，逐项断言）；
3. `travel_min` 是 6 × 6 完整矩阵、对称、对角线为 0；A、B、H1、H2 之间的值与 V1 相同；满足三角不等式（任意两点直达不比经第三点绕行更远）；
4. `api.load_config('config/medical_resources_v1_1')` 通过 SHA 校验。

**场景**

5. `run_002` 的 `patient_specs.json`、`patients_initial.json` 与 `run_001` 相比，只有 `location_id` 不同，且替换规则正确；模板和 16 个观测文件逐字节相同；
6. `api.load_cases('dataset_v1/run_002')` 能正常加载 16 人，地点均为 F1 或 F2。

**校验器对阵地的处理**

校验器要求所选方案中的每个动作都被排上，所以这组测试用**只有一个动作、且非持续性**的伤员：P10（开放性气胸，F1，第 10 分钟受伤，方案只有 `occlusive_dressing`）和 P05（张力性气胸，F2，第 0 分钟受伤，方案只有 `needle_decompression`）。用 `api.build_input` 构造只含这一两名伤员的 `dispatch_input`，手写排程做断言。排程为 `demonstration_only: true`：

7. P10：V1 从 A 出发（`start_min ≥ 10`），按 `start + 8`（空驶）`+ 3`（装载）`+ 8`（F1→A）`+ 5`（交接）`+ 5`（周转）把 P10 接到 A，交接结束后在 A 的处置位做 `occlusive_dressing`，校验通过、0 冲突；
8. 把 7 中的 `occlusive_dressing` 改到 F1、在装车之前做，被拒绝（`LOCATION_UNSUPPORTED`）；
9. 把 7 中的 `occlusive_dressing` 改到车上（`location = "V1"`，使用 V1 的担架位、随车人员和车上库存），时间完全落在装载开始到交接结束之间，校验通过；
10. P05：V2 从 B 出发，到 F2 接 P05 送回 B；在这趟车程中于车上（`location = "V2"`）做 `needle_decompression`，被拒绝（`LOCATION_UNSUPPORTED`）；
11. 7 中车辆的 `start_min` 早于 P10 的受伤时刻（第 10 分钟），被拒绝（`BEFORE_ARRIVAL`）；
12. 7 中的接人点写成 A 而不是 F1，被拒绝（`PATIENT_LOCATION`）。

若某条断言因校验器的其他规则（不是阵地相关）而无法按写法成立，在报告中说明实际报出的冲突码，不要修改校验器。

**场景选择与脱水**

13. `runner` 的场景参数：`run_001` 的行为与改动前完全一致（V1 的全部 `agent_chain` 测试继续通过）；`run_002` 加 `native_replay` 或 `offline` 时直接报错；
14. 脱水伤员走初始化路径：用假引擎断言调用了带 `configuration` 的初始化、没有提交动态伤情；
15. （`integration`）P08 用原生 Pulse 初始化成功，并推进 5 分钟仿真时间不失败。

---

## 6. 验收

全部满足才算完成：

1. 全量非 integration 测试和 integration 测试全部通过；
2. `bash scripts/validate.sh` 退出码为 0；`python scripts/verify_offline.py` 结果与改动前完全一致；
3. 重新跑一次 `run_001` 的 `native_replay`：**16 名伤员全部进入仿真**（P08 不再是 `INJURY_UNSUPPORTED`）。报告 16 人结局表，格式同 V1 验收报告 §5；并单独列出与 V1 验收运行（`agent_chain_v1_native_replay_002`）相比，除 P08 外有没有任何伤员的结果发生变化（应当没有）；
4. 用 `run_002` 构造完整的 `dispatch_input`（16 人），保存到运行目录之外的报告附件中，并报告：每名伤员的地点与受伤时刻、候选方案数；
5. 未修改 §0.2 列出的受保护路径。

`run_002` 的端到端运行**不在本次范围内**：目前唯一不调用模型的排程来源是 DeepSeek 的回放排程，它只对 `run_001` 有效。`run_002` 的排程需要真实模型（`live`）或以后的 CP-SAT 求解器，需用户另行决定。

---

## 7. Git 与报告

- 从本文所在的提交新建分支 `codex/field-nodes-v1-1`；
- 按功能分成若干提交；
- 推送到 GitHub，**不要合并到 main**；
- 不提交运行输出、`.env`、凭据。

报告内容：

1. 分支名和提交列表；
2. 测试结果（通过、失败、跳过数）；`validate.sh`、`verify_offline.py` 的结果；
3. §6 第 3 条的 16 人结局表，以及与 V1 验收运行的逐人对比；
4. §6 第 4 条的 `run_002` 伤员列表；
5. 与本文不一致的地方，逐条列出原因；
6. 待决问题。
