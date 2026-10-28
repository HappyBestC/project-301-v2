# 阵地资源模型 V1.1 实现与验收报告

§6 验收完成。分支为 `codex/field-nodes-v1-1`，从规格提交 `7d26420` 建立。
V1.1 新增 F1/F2 阵地及 run_002，Agent 链路可选择场景；P08 脱水改由现有
Pulse 初始化配置设置，16 名伤员现已全部进入仿真。

## 1. 实现

- `config/medical_resources_v1_1/`：actions.json 与 V1 逐字节相同；resources.json
  仅变更版本、F1/F2 节点、完整路程矩阵和追加说明。阵地无资源、不允许启动处置。
- `dataset_v1/run_002/`：两个患者索引仅改 location_id（A → F1、B → F2），
  模板和 16 份观测逐字节复制，不复制 raw 或 evaluation_evidence。
- `agent_chain/scenarios.py` 注册场景；runner 增加 `--scenario`，默认 run_001。
  场景目录贯穿节点、模板准入、回放 Provider 和执行桥。manifest 保存场景名、
  配置/数据目录及目录下每个文件的 SHA256。
- run_002 的 offline/native_replay 在 Provider 和运行目录创建前报错，
  不会套用 run_001 的 DeepSeek 排程。本次没有进行 run_002 端到端运行。
- 脱水调用 `PatientInitializer().configuration(casualty)`，将结果传给
  `ResearchPulseSession.initialize(configuration=...)`。之后稳定 60 秒，
  不再提交动态伤情。该条件包含稳定期的时序简化写入 manifest；其他伤情路径不变。

现有适配器和 session 直接可用，无需修改。依赖未变，LangGraph 保持 1.2.18。

## 2. 功能提交

| 提交 | 内容 |
|---|---|
| 354a123 | V1.1 阵地资源、run_002 数据与原配置/数据一致性、校验器测试 |
| d630f8f | 场景注册、参数贯穿、无排程拒绝、输入文件 SHA 审计与场景测试 |
| df5cb75 | 脱水初始化条件及假引擎、原生 Pulse 验证 |

本报告更新单独提交。完整提交列表和最终推送核验保存在本地验收报告中。

## 3. 验收

| 检查 | 通过 | 失败 | 跳过 | 结果 |
|---|---:|---:|---:|---|
| 全量非 integration | 1383 | 0 | 0 | 包含原有测试与新增 27 项；28 项 integration 未选中 |
| 全量 integration | 28 | 0 | 0 | 新增 P08 初始化和稳定后 5 分钟原生推进 |
| bash scripts/validate.sh | — | — | — | 退出码 0 |
| python scripts/verify_offline.py | — | — | — | 退出码 0，结果与改动前逐字段相同 |

两组 pytest 各有 6 个既有 Pulse/pkg_resources 弃用警告；没有 xfail 或跳过。
旧 P08 不支持测试改为通用适配器失败注入，继续覆盖不支持伤情的异常路径，
另增脱水初始化路径测试，未删除该错误处理分支的验证。

verify_offline 保持 16 人、25 个操作、8 次转运、82 个照护任务、0 冲突、
54 项 unchecked、fully_verified=false；输入重建与回放验证相同，未修改源状态，
未加载 Pulse。validate.sh 产生的跟踪输出已恢复原内容。

原生验收运行 `field_nodes_v1_1_native_replay_001` 的 manifest 记录干净提交
`df5cb752b48302a51aec0e609005733f781d5a4f`。状态为 `completed`；
16 人全部进入仿真，INJURY_UNSUPPORTED 为 0，
引擎失败为 0。P07、P16 的 exploratory 标记沿用 V1。

与 `agent_chain_v1_native_replay_002` 比较：除 P08 外，其余 15 名伤员的所有结局字段、
逐点采样、事件和动作记录均精确相等，没有使用数值容差掩盖差异。
P08 从 not_simulated 变为 complete。
运行 SHA 清单和场景源文件 SHA 全部核验通过。

run_002 的完整 16 人 dispatch_input 及每人地点、受伤时刻、候选方案数已保存为
报告附件，位于原生运行目录之外。阵地/车辆测试的 6 种排程均满足规格断言；
完整拒绝码保存在附件，没有修改校验器或放宽断言。

## 4. 完整报告与附件

以下路径相对仓库根目录，位于 Git 忽略目录，仅保存在服务器，未提交运行输出：

- `experiments/results/agent_chain/field_nodes_v1_1_report/FIELD_NODES_V1_1_ACCEPTANCE_REPORT.md`：
  完整提交列表、测试结果、原生 summary、16 人结局表、V1 逐人比较、run_002 伤员列表和推送核验。
- `experiments/results/agent_chain/field_nodes_v1_1_report/run_002_dispatch_input.json`：完整输入附件。
- `experiments/results/agent_chain/field_nodes_v1_1_report/v1_patient_comparison.json`：逐字段比较。
- `experiments/results/agent_chain/field_nodes_v1_1_report/acceptance_verification.json`：原始数据与文件完整性核验。
- `experiments/results/agent_chain/field_nodes_v1_1_native_replay_001/`：完整原生执行留痕。

复现使用 `source scripts/activate.sh`，再执行
`python -m core301.agent_chain.runner --mode native_replay --scenario run_001 --run-id NEW_ID`。
运行 ID 必须未使用过。

## 5. 差异、保护范围与待决问题

与规格不一致之处：无。待决问题：无。run_002 未来的真实排程按规格留待另行决定，
不属于本次范围内的未完成事项。

未修改 `config/medical_resources_v1/`、`dataset_v1/run_001/`、
`src/core301/dispatch/minimal/`、`research_artifacts/`、`research_baseline/`、
`src/core301/pulse/`。没有合并到 main，没有运行 live 或发起真实模型请求；
运行输出、.env 和凭据均未提交。
