# Agent 链路 V1 实现与验收报告

状态：实现及 §11 验收完成。分支为 `codex/agent-chain-v1`，未合并到 `main`，
未运行 `live`，未发起真实模型请求。本报告取代此前的暂停报告。
完整验收数据保存在服务器的忽略目录，见第 6 节。

## 1. 采用的规格与用户决定

在本分支执行 `git fetch origin` 和
`git merge --ff-only origin/claude/agent-chain-spec`，快进到 `ca27742`，
采用更新后的 §6.2 和 §7。

用户随后明确指定 LangGraph 为 `1.2.18`；并解决了 §5.2 与 §10 的协议引用冲突：
按 `(injury_type, action_type)` 从现有模板原样复制 `fixed_protocol_ref`，
保留 `protocol_id`、`source`、`action_selector` 等完整字段。
实现遵循这一明确答复，未修改源模板。16 名伤员的候选方案和完整调度输入
均通过逐字段一致性测试。规格原文未改写，此处记录有效的用户补充决定。

## 2. 实现内容

新增 `src/core301/agent_chain/`，使用实际 LangGraph `StateGraph` 连接八个节点，
处理处置排除、调度冲突反馈、独立复验、执行时间线和结局汇总。
处置合同采用严格 JSON/Pydantic 校验；模板、Fake、LLM Provider 共用准入逻辑。
LLM 接口沿用现有 OpenAI SDK，保存请求、响应、usage 和 prompt SHA，调用失败不重试。

Pulse 桥为每名伤员启动独立进程，复用冻结状态与现有伤情、救助参数，
按操作结束时刻注入，以原生回执判断接受结果。安装的原生绑定通过
`process_actions` 提交 `AdvanceTime`，由 C++ 整段推进，没有 Python 单步循环
或现实时间等待。事件解码遵守 protobuf 的省略默认值规则。

结局明确区分完整窗口、终末事件、引擎失败和伤情不支持；观察积分与终末窗口
积分分别计算，未知后续状态不补零。审计包括节点快照、逐调用记录、逐人执行、
结局、汇总和文件 SHA。运行目录已存在时拒绝覆盖。

## 3. 功能提交

基准规格提交为 `ca27742`。下表列出其后的代码与历史报告提交；本报告更新
作为单独的文档提交。含最终文档提交的完整列表保存在第 6 节的本地验收报告。

| 提交 | 内容 |
|---|---|
| 215e51c | 固定 LangGraph 1.2.18 和传递依赖，忽略运行输出、打包 prompt |
| 0c71bf8 | 处置合同、准入、Provider、状态与审计 |
| 3bf94e1 | 时间线、独立 Pulse 进程与结局计算 |
| 5240aff | LangGraph 节点、边与模式入口 |
| afcb4b8 | 记录协议引用冲突和当时失败的验收测试；现已由用户决定解决 |
| bca5e4c | 按伤情和动作原样保留模板协议引用 |
| 2b103cc | 覆盖图路由、准入、原生回执、结局与模型调用审计 |
| 010446b | 正确解码原生事件省略的 protobuf 默认值 |
| 1907f4c | 分离观察积分与终末时刻截断积分，并增加边界测试 |

## 4. 精确依赖

原有锁定版本未改动。`pyproject.toml` 固定 `langgraph==1.2.18`，
`requirements.lock.txt` 新增以下 24 项。LangGraph 的 38 项依赖闭包均已核对
安装版本与锁文件一致，`pip check` 通过。未使用 LangChain 的模型封装。

```text
charset-normalizer==3.5.2
httpcore2==2.16.0
httpx2==2.16.0
jsonpatch==1.38
jsonpointer==3.6
langchain-core==1.7.0
langchain-protocol==0.0.20
langgraph==1.2.18
langgraph-checkpoint==4.3.1
langgraph-prebuilt==1.1.1
langgraph-sdk==0.4.10
langsmith==0.14.14
orjson==3.13.0
ormsgpack==1.13.0
pyyaml==6.0.3
requests==2.34.2
requests-toolbelt==1.0.0
tenacity==9.2.1
truststore==0.10.5
urllib3==2.8.0
uuid-utils==0.19.0
websockets==17.3
xxhash==4.0.2
zstandard==0.25.0
```

## 5. 验收结果

| 检查 | 通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| 全量非 integration | 1356 | 0 | 0 | 原有 1252 项及新增 104 项；27 项 integration 未选中 |
| 全量 integration | 27 | 0 | 0 | 原有 26 项及新增独立原生引擎测试 |
| `bash scripts/validate.sh` | — | — | — | 退出码 0，包含上述非 integration 测试及原有检查 |
| `python scripts/verify_offline.py` | — | — | — | 退出码 0，结果与基线一致 |
| 参数来源一致性 | 12 | 0 | 0 | 包含在非 integration 总数中，覆盖 7 类开放伤情的允许动作 |

两组 pytest 各有 6 个已有 Pulse/pkg_resources 弃用警告；没有 xfail 或以跳过
替代验收。`verify_offline.py` 保持：16 人、25 个操作、8 次转运、82 个照护任务、
0 冲突、54 项 unchecked、`fully_verified=false`；输入重建及验证回放相等，
源状态未变，未加载 Pulse。

`offline` 验收运行 `agent_chain_v1_offline_002` 为 `completed`。
`native_replay` 验收运行 `agent_chain_v1_native_replay_002` 有 16 人进入执行，
15 人完成窗口；P08 按 §6.2 记为 `INJURY_UNSUPPORTED`，整体为
`execution_partial`。无引擎失败、无已记录终末事件，24 个已注入动作均被接受。
P07、P16 按规格标为 `exploratory`。

两次完整回放均由干净提交 `010446b` 启动，原始 manifest 保留该提交号。
后续 `1907f4c` 修正仅影响终末时刻落在采样间隔内的积分边界；使用最终评价代码
对两次保存的完整执行记录重算，结局逐字段相同。非 integration 全量测试在
`1907f4c` 上通过；integration 验证的执行桥在该提交中未改动。
两次运行分别核验了 132、147 个文件的 SHA，原始运行文件未改写。

## 6. 完整运行报告与复现

以下文件仅存在于服务器仓库的 `experiments/results/agent_chain/` 忽略目录，
不在 GitHub 分支中。路径相对仓库根目录：

- `experiments/results/agent_chain/AGENT_CHAIN_V1_ACCEPTANCE_REPORT.md`：完整提交列表、
  精确依赖、两份原始 `summary.json`、16 人结局表、原因和验收证据路径。
- `experiments/results/agent_chain/agent_chain_v1_offline_002/`：offline 验收留痕。
- `experiments/results/agent_chain/agent_chain_v1_native_replay_002/`：native_replay 验收留痕。
- `experiments/results/agent_chain/acceptance_checks_final/`：最终非 integration、
  validate、verify_offline、来源/依赖和运行文件核验。
- `experiments/results/agent_chain/acceptance_checks_v2/integration.xml`：integration 结果。

复现使用 `source scripts/activate.sh` 激活 Python 3.11 与原生 Pulse 环境，
再运行 `python -m core301.agent_chain.runner --mode offline --run-id NEW_ID`
或 `--mode native_replay`。运行 ID 必须未使用过。

## 7. 与规格原文的差异及待决问题

- §5.2 的统一 `fixed_protocol_ref` 表达式按用户明确答复替换为模板完整字段；
  这是已批准的规则修正，用于满足 §10 逐字段一致性。
- §1 的版本选择按用户明确指令收敛为 LangGraph `1.2.18`。
- P08 的脱水只能作为初始化 Condition；现有动态适配器返回
  `CONDITION_REQUIRES_INITIALIZATION: Dehydration cannot be submitted as an Injury Action`。
  按 §6.2、§7 记录为未仿真，两个积分均为 null，未改变初始化顺序或适配器。
  这是规格规定的执行结果，不是引擎失败，也不能据此推断 P08 的生理结局。
- 无 `ACTION_UNSUPPORTED`。血胸的已知限制及观测来源简化已进入 manifest。
- §2 禁止修改的所有路径均无变更；运行输出、`.env` 和凭据均未提交。

待决问题：无。未采用未经用户授权的设计例外。
