# Agent 链路 V1 实现进度与阻塞报告

状态：**开发暂停，§11 验收未完成，分支是未验收初稿。**

已按要求在 `codex/agent-chain-v1` 上执行 `git fetch origin` 和
`git merge --ff-only origin/claude/agent-chain-spec`，快进到规格提交
`ca27742`，重读并采用更新后的 §6.2 和 §7。

## 1. 待决问题：协议引用规则与逐字段验收冲突

规格 §5.2 明确规定所有候选动作生成：

```json
{"protocol_id": "{action_type}.phase1.1", "source": "src/core301/pulse/v2/protocol_book.py"}
```

但 §10 第 3、4 条同时要求 Template 生成的候选方案及调度输入与
`api.load_cases()`、已有 `dispatch_input.json` 逐字段一致。现有数据中有以下例外：

| 伤员 | 动作 | 模板中的 protocol_id | 模板中的 source |
|---|---|---|---|
| P04 | remove_from_exposure | 301.v2.co.removal.restricted.1 | src/core301/runtime/v2/exposure_validation.py |
| P07、P16 | control_hemothorax_bleeding、chest_tube | 301.v2.hemothorax.restricted.1 | src/core301/runtime/v2/hemothorax_validation.py |
| P12 | supplemental_oxygen | oxygen.alveolar.nc05.phase1.1 | src/core301/pulse/v2/protocol_book.py |
| P14 | remove_from_exposure | 301.v2.hypoxia.removal.restricted.1 | src/core301/runtime/v2/exposure_validation.py |

暴露和血胸动作的模板引用还包含 `action_selector`，值为对应动作类型。
因此照 §5.2 的固定表达式生成会使五名伤员、七个动作的协议引用不一致。
§2 又禁止修改这些模板和已冻结数据。

**需要决定**：是否按 `(injury_type, action_type)` 从现有模板原样复制
`fixed_protocol_ref`（包括 `source`、`action_selector`），以满足逐字段一致；
或者保留 §5.2 表达式并调整一致性验收。尚未擅自采用任一例外规则。

当前实现保留 §5.2 的字面表达式，测试公开失败，没有使用 xfail、跳过或放宽断言。

复现命令：

```bash
source scripts/activate.sh
python -m pytest -q tests/agent_chain/test_spec_compatibility.py --tb=short -p no:cacheprovider
```

## 2. 分支与提交

分支：`codex/agent-chain-v1`。未合并到 `main`。

| 提交 | 内容 |
|---|---|
| ca27742 | 从规格分支快进合入两项待决问题的解决方案 |
| 215e51c | 固定 LangGraph 1.2.18 及传递依赖，忽略运行输出并打包 prompt |
| 0c71bf8 | 处置合同、准入、Provider、状态和审计初稿 |
| 3bf94e1 | 时间线、独立进程 Pulse 桥、缺失值明确的结局计算初稿 |
| 5240aff | LangGraph 编排、节点和三种模式入口初稿 |

本报告与规格兼容性测试在随后的报告提交中；完整提交号可用
`git log --oneline ca27742..codex/agent-chain-v1` 查看。

初稿按文档文件布局写入，但除下列检查外尚未完成测试覆盖和端到端验证。
阻塞解除后仍需补全 §10 其他测试、修正测试暴露的问题并执行全部 §11 验收。

## 3. 精确依赖版本

LangGraph 已从服务器包源安装，使用现有锁文件作为约束；未改动原有锁定版本。
以下 24 个新增包均已写入 `requirements.lock.txt`，主依赖写入 `pyproject.toml`。
`pip check` 通过。没有使用 LangChain 模型封装；`langchain-core` 等由 LangGraph 传递引入。

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

## 4. 检查结果

| 检查 | 结果 |
|---|---|
| 原有非 integration 测试，排除新增 tests/agent_chain | 1252 通过、0 失败、0 跳过、26 未选中；6 个已有弃用警告；134.14 秒 |
| 新增规格兼容性测试 | 23 通过、6 失败、0 跳过；0.76 秒 |
| 两来源 Pulse 动作参数比较 | 上述新增测试中的 12 项全部通过，覆盖 7 类开放伤情的允许动作 |
| python scripts/verify_offline.py | 退出码 0，结果与既有基线一致 |
| python -m compileall -q src/core301/agent_chain | 退出码 0，仅证明语法可编译 |
| git diff --check | 通过 |
| integration 测试 | 未运行 |
| bash scripts/validate.sh | 未运行，已因规格冲突停止后续验收 |

新增六个失败分别为 P04、P07、P12、P14、P16 的候选方案逐字段比较，
以及完整调度输入的伤员列表比较。其余十一名伤员的候选方案逐字段一致。

`verify_offline.py` 仍得到：16 名伤员、25 个操作、8 次转运、82 个照护任务、
0 冲突、54 项 unchecked、`fully_verified=false`、输入未变、未加载 Pulse，
输入重建和验证回放均相等。此检查验证已有基线，不代表新链路已通过验收。

独立原生接口探测确认：已安装的 Pulse 4.3.2 可以通过
`process_actions` 提交 `AdvanceTime` 动作，在 C++ 内整段推进 60 秒。
没有修改绑定，也没有用 Python 单步循环替代整段推进。

## 5. 运行结果与结局表

`offline` 和 `native_replay` 的完整链路均未运行，因此没有两次运行的
`summary.json`，也没有 §11 第 4 条要求的 16 人结局表。不能据接口探测或
合成信号宣称验收完成。

另已确认现有动态伤情适配器拒绝脱水：
`Dehydration cannot be submitted as an Injury Action`。初稿按 §6.2 的
“冻结状态稳定 60 秒后施加伤情”顺序处理，不改为带 Condition 重新初始化；
P08 在真实执行时将按已规定的规则记录 `INJURY_UNSUPPORTED`，积分为 null。
这目前是适配器检查结论，不是一次完整运行的结局。

## 6. 与规格不一致及保护范围

- 未满足 §10 第 3、4 条：原因是第 1 节列出的 `fixed_protocol_ref` 冲突。
- 尚未完成 §10 其他测试及 §11 全部验收；代码明确标记为初稿，不宣称完成。
- §2 禁止修改的目录和文件均未修改，包括现有 Pulse 模块和外部 Pulse 安装。
- 没有修改数据、资源规则或校验器；没有运行 live，没有发起真实模型请求。
- 不提交任何运行输出、`.env` 或凭据。原生接口探测日志位于 `/tmp`，未进入 Git。
