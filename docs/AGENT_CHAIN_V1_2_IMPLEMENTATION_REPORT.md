# Agent 链路 V1.2 实施前待决报告

状态：**遇到规格未明确的流程边界，按要求停止实现；尚未完成验收。**

已执行 `git fetch origin`，从规格所在提交
`837d7a49f2c21796cf9edee8a150fc3377fb5429`
（`origin/claude/agent-chain-v1-2-spec`）新建分支
`codex/agent-chain-v1-2`。开始时工作区干净，`main` 为
`f71377d59ed5ca1e86453bec874d135aaa334811`。

采用的规格为 [AGENT_CHAIN_V1_2_REVISION_SPEC.md](AGENT_CHAIN_V1_2_REVISION_SPEC.md)，
同时核对了其继承的 [V1 开发文档](AGENT_CHAIN_V1_DEV_SPEC.md)、现有图和节点实现、
处置 Provider、结局计算及相关测试。规格要求：

> 本文没有写到、需要做设计决定的地方，**停下来写进报告的"待决问题"，不要自行发挥**。

因此本次只新增这份报告，没有改动实现、测试或规格，也没有自行选定下列行为。

## 待决问题

### 1. 调度提前出错时的执行走向和已有部分排程

现有 [nodes.py](../src/core301/agent_chain/nodes.py) 的 `validate` 对以下情况立即停止调度，
不等到 `max_schedule_attempts`，并清空本次接受结果：

- 请求异常：`SCHEDULE_REQUEST_FAILED`；
- Provider 校验结果与宿主独立校验不一致：`PROVIDER_VALIDATION_MISMATCH`。

V1 §4 明确要求 Provider 校验不一致时“记为错误并停止”。现有
[test_graph.py](../tests/agent_chain/test_graph.py) 的
`test_provider_validation_disagreement_stops_immediately` 和
`test_request_exception_is_not_retried_or_leaked` 覆盖了这些提前停止行为。

V1.2 §2 规定达到轮数上限后选择最大的无冲突部分排程；§3.1 列出的调度改边条件是
“达到轮数上限，且没有任何 0 冲突的轮次”，随后又说明“处置或调度失败后不再直接结束”
和“其余边不变”。这没有明确上述两类提前停止是否也进入无治疗仿真。

一个具体场景是：第 1 轮已有 0 冲突、排入 12 人的候选，第 2 轮请求异常，轮数上限为 3。
另一个场景是：第 1 轮宿主校验 0 冲突，但 Provider 返回的校验结果与宿主不一致。
不同处理会改变是否产生结局、是否施加治疗以及最终运行状态，需要明确：

1. 两类错误是否仍立即停止后续调度调用；
2. 停止后是整次运行 `aborted`、不执行 Pulse，还是进入 `build_timeline` 并评价全部伤员；
3. 如果继续仿真且此前已有无冲突部分排程，是采用已有候选，还是所有伤员无治疗。

尚未为这些情况选择策略、增加回退或改写旧测试。

### 2. 提前 aborted 时两个阶段字段如何表示

V1.2 §3.4 增加 `treatment_stage` 和 `schedule_stage`，但没有说明阶段尚未开始或尚未结束时
的值。例如：运行目录已创建，`load_scenario` 抛出异常，两个 Agent 都尚未运行。

此时 `status=aborted` 已有明确定义，但 `treatment_stage` 的 `ok / partial / failed`
和 `schedule_stage` 的 `full / partial / failed / skipped` 均没有定义“尚未开始”；
其中 `skipped` 被限定为“处置全部失败，未调用调度”。

需要明确 aborted 的 summary 是否允许省略尚无结果的阶段字段、允许 `null`，
或采用其他明确表示。没有自行增加枚举值，也没有把“尚未执行”写成“全部失败”。

## 实施、测试与验收状态

| 项目 | 本次状态 |
|---|---|
| 处置 token 上限与五类失败原因 | 未修改，等待上述边界确认后继续实施 |
| 部分排程选择、全员仿真、结局和阶段字段 | 未修改 |
| 功能提交 | 无；唯一新增提交为本待决报告 |
| 全量非 integration 测试 | 未运行；不将旧结果冒充本次验收 |
| 全量 integration 测试 | 未运行 |
| `bash scripts/validate.sh` | 未运行 |
| `python scripts/verify_offline.py` | 未运行 |
| §5.2 run_001 native_replay 及逐人 V1.1 对比 | 未运行，未生成对比结论 |
| §5.3 部分排程 offline 运行、summary、分组汇总 | 未运行，未生成产物 |
| live 或真实模型请求 | 未运行、未调用 |

与规格的已实施差异：没有实施变更。§5 验收尚未完成；以上问题未确定前，不报告为实现完成。

## Git 与数据边界

本报告按 §6 提交并推送到 `codex/agent-chain-v1-2`，供规格澄清和后续实施使用；
推送结果与提交号在执行回报中列明。不合并到 `main`。

除本报告外，没有修改受跟踪文件。未修改 `.env`、凭据、既有运行输出、资源配置、数据集、
校验器或 Pulse 模块，未提交任何运行输出或凭据。
