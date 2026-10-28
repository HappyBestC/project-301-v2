# Agent 链路 V1.2 实施与验收报告

按修订规格 `bfee530d6ca813e45731305e7c1864d32d2e9588` 实现，§5 验收全部通过。
分支为 `codex/agent-chain-v1-2`；功能验收基于干净工作区提交
`ff13aee001fae289f46cc6ca553ba7abed958cb6`。本次没有运行 live，也没有发起真实模型请求。

## 1. 分支与功能提交

已在功能分支执行 `git fetch origin` 及
`git merge --no-edit origin/claude/agent-chain-v1-2-spec`，合入修订后的 §2.1 和 §3.4。

| 提交 | 内容 |
| --- | --- |
| `bfee530` | 规格修订：调度错误路径与 aborted/not_reached 阶段语义 |
| `76f3fc2` | 在功能分支合入修订规格 |
| `b888bbe` | 处置输出预算参数、五类失败原因与对应测试 |
| `ff13aee` | 部分排程选择、全员仿真、阶段状态、结局分组与对应测试 |

本报告单独提交；最终报告提交号及远端核验记录见交付回复和本地完整验收报告。
目标远端为 `origin/codex/agent-chain-v1-2`。不合并到 `main`；
`main` 与 `origin/main` 保持 `f71377d59ed5ca1e86453bec874d135aaa334811`。

## 2. 实现结果

- `LLMTreatmentProvider` 的输出预算默认 8192，runner 接受
  `--treatment-max-tokens`（256–32768），实际预算写入 manifest。
  根据 provider 的真实 `finish_reason` 和请求/准入结果区分
  `OUTPUT_TRUNCATED`、`EMPTY_RESPONSE`、`CALL_FAILED`、`JSON_INVALID`、`ADMISSION_REJECTED`；
  保留错误类型、状态码或准入原文 detail。每人一次，不重试、不使用模板替补。
- 原来的立即接受条件保留；达到轮次上限后选择排入人数最多的零冲突候选，同人数取最早轮次。
  候选中未排入者的 `reason_code`、`reason`、`considered_alternatives` 原样保留。
- 调度请求异常立即停止后续调用，选择此前最优零冲突候选并继续全员仿真，记录 `schedule_error`。
  模型正文无效仍作为一轮冲突；Provider 校验不一致则整次 `aborted`，没有执行和结局。
- 16 人均有 `injury_onset`。未治疗者只有受伤事件，四种治疗状态进入执行和评价；
  处置排除者不进入调度、不占资源，manifest 已注明。选中空方案的 `no_treatment_needed` 仍为 `scheduled`。
- 原有两种 ∫CO 口径不变，增加状态人数和按状态分组的总和、均值、分母、死亡及休克人数。
  未治疗本身不是排除理由。`treatment_stage`、`schedule_stage` 始终存在；
  `completed`/`execution_partial` 退出 0，`aborted` 退出 1。

修改限于 `src/core301/agent_chain/`、`tests/agent_chain/` 及本报告。
调度请求参数、独立调度校验器、数据集、资源配置和 Pulse 模块均未改动。

## 3. 测试与离线核验

| 检查 | 通过 | 失败 | 错误 | 跳过 | JUnit 耗时（秒） |
| --- | --- | --- | --- | --- | --- |
| 全量非 integration | 1423 | 0 | 0 | 0 | 167.096 |
| 全量 integration | 28 | 0 | 0 | 0 | 406.148 |
| validate.sh 中的 M2 子集 | 678 | 0 | 0 | 0 | 14.211 |

非 integration 和 integration 各有 6 条 `DeprecationWarning`，原文保存在各自日志中，
涉及 `pkg_resources` 与 `declare_namespace`。没有失败或跳过。

`bash scripts/validate.sh` 退出 **0**，进程耗时 **196.8947121053934 秒**；
包括上述全量非 integration 测试。脚本生成的验收文件已另存到忽略目录，
原有 `validation/` 的 8 个文件均恢复到运行前内容，逐文件 SHA-256 一致。

`python scripts/verify_offline.py` 退出 **0**，结果不变：

```json
{
  "input_rebuilt_equal": true,
  "validation_replay_equal": true,
  "patients": 16,
  "operations": 25,
  "transports": 8,
  "care": 82,
  "conflicts": 0,
  "unchecked": 54,
  "fully_verified": false,
  "source_state_mutated": false,
  "Pulse_loaded": false
}
```

新增测试覆盖输出预算传递和边界、五类失败原因、部分排程最大覆盖及最早轮次、
调度请求失败与校验不一致、阶段中止、四种治疗状态、空方案、原有分母及分组计算。
模型请求均使用假 Provider 或 SDK mock。

## 4. run_001 native_replay 与 V1.1 逐人比较

基准为 `field_nodes_v1_1_native_replay_001`；本次为
`agent_chain_v1_2_native_replay_001`。进程退出 **0**，
现实耗时 **793.479942606762 秒**；runner 耗时
**792.081979139708 秒**。结果为 `completed / ok / full`，
1 轮、0 冲突、16 人排入、16 人完成，全部 `scheduled`。

每人原有 **19 个字段逐值精确相等，不使用数值容差**。比较覆盖动作数、终末事件、首次休克、
window_status、两项 ∫CO、最终 MAP/BloodVolume 和各项标志及原因。
新增的治疗状态和原因字段不参与旧字段比较。

| 伤员 | 原有结局字段比较 | 新增 treatment_status | window_status | ∫CO（L；V1.1 = V1.2） |
| --- | --- | --- | --- | --- |
| P01 | 19 / 19 完全相同 | scheduled | complete | 726.5201058127102 |
| P02 | 19 / 19 完全相同 | scheduled | complete | 618.1394032452956 |
| P03 | 19 / 19 完全相同 | scheduled | complete | 703.0461736444986 |
| P04 | 19 / 19 完全相同 | scheduled | complete | 702.6219900436375 |
| P05 | 19 / 19 完全相同 | scheduled | complete | 604.2396896857765 |
| P06 | 19 / 19 完全相同 | scheduled | complete | 587.5066303663571 |
| P07 | 19 / 19 完全相同 | scheduled | complete | 683.3510285407137 |
| P08 | 19 / 19 完全相同 | scheduled | complete | 705.2025756441597 |
| P09 | 19 / 19 完全相同 | scheduled | complete | 664.2170499432821 |
| P10 | 19 / 19 完全相同 | scheduled | complete | 497.3489659423808 |
| P11 | 19 / 19 完全相同 | scheduled | complete | 453.7083146045816 |
| P12 | 19 / 19 完全相同 | scheduled | complete | 642.8052212769603 |
| P13 | 19 / 19 完全相同 | scheduled | complete | 583.1771015438458 |
| P14 | 19 / 19 完全相同 | scheduled | complete | 583.6450436111338 |
| P15 | 19 / 19 完全相同 | scheduled | complete | 559.7079912914431 |
| P16 | 19 / 19 完全相同 | scheduled | complete | 549.1993113574655 |

16 人的 `samples.csv`、`actions.json`、`events.json` 共 48 个文件也逐字节相同。
9 个原有汇总字段完全一致：死亡 0 人、休克 0 人、引擎失败/伤情不支持/治疗不完整均为 0，
P07、P16 保持 exploratory。全部可用 ∫CO 为
**9864.436596554244 / 616.5272872846402 / 16**（总和 / 均值 / 分母）；
干净口径为 **8631.886256656064 / 616.5633040468617 / 14**，排除原因仍仅为 P07、P16 exploratory。

原基准全部 149 个文件保持原 SHA-256；本次 148 个产物摘要和 51 个场景输入摘要均已核验。
详细比较保存在本地 `native_outcome_comparison.json`。

补充完整 offline 运行 `agent_chain_v1_2_offline_001`：`completed / ok / full`，
16 人排入并完成；与 `agent_chain_v1_offline_002` 的原有逐人结局完全一致。

## 5. 部分排程 offline 验收

运行 `agent_chain_v1_2_partial_offline_001` 使用 FakeTreatmentProvider、FakeSchedulingProvider
和 FakePulse；脚本同时禁止构造 OpenAI 客户端。为 P01、P04、P05、P08 构造未排入结果，
其他 12 人保留原排程。3 轮均为 12 人、0 冲突；轮次达到上限后接受第 1 轮。
以下为 summary 字段及分组汇总；**summary.json 原文**包含在本地完整验收报告中。

| summary 项目 | 值 |
| --- | --- |
| run_id / mode | agent_chain_v1_2_partial_offline_001 / offline |
| status / treatment_stage / schedule_stage | completed / ok / partial |
| horizon_min | 120.0 |
| loaded_patients / accepted_patients / execution_patients | 16 / 12 / 16 |
| schedule_attempts / last_conflicts | 3 / 0 |
| 最终接受轮次 | 1 |
| excluded_patients | {} |
| model_calls_enabled / synthetic_physiology | false / true |
| window_status_counts | complete=16；其他状态均为 0 |
| deaths / engine_failures / injury_unsupported / treatment_incomplete | 0 / 0 / 0 / 0 |
| exploratory | 2（P07、P16） |
| all_available：总和 / 均值 / 分母 | 9000.0 / 562.5 / 16 |
| clean：总和 / 均值 / 分母 | 7900.0 / 564.2857142857143 / 14 |
| wall_elapsed_s（runner） | 4.2247843984514475 |

| treatment_status | 人数 | ∫CO 总和（L） | 均值（L） | 分母 | 死亡人数 | 休克人数 |
| --- | --- | --- | --- | --- | --- | --- |
| scheduled | 12 | 6600.0 | 550.0 | 12 | 0 | 0 |
| unscheduled | 4 | 2400.0 | 600.0 | 4 | 0 | 0 |
| treatment_excluded | 0 | 0 | null | 0 | 0 | 0 |
| no_schedule | 0 | 0 | null | 0 | 0 | 0 |

4 名未排入者均只有 `injury_onset`，完成 120 分钟窗口，动作注入/接受/不支持数均为 0，
并进入全部可用和干净口径的分母。每人的 ∫CO 为 600.0 L。
未排入原始值在最终排程中保留：

- `reason_code`: `no_feasible_schedule_found`
- `reason`: `The provider has not completed verification of all treatment alternatives.`
- `considered_alternatives`: `["Reviewed the treatment alternatives but did not complete all checks."]`

两种原有口径中，干净口径仍仅排除 P07、P16 的 exploratory 标记。
以上生理值来自 FakePulse（`synthetic_physiology=true`），用于验证流程与分母。
完整 offline 的 132 个产物摘要、部分排程的 144 个产物摘要全部核验通过。

## 6. 产物与边界

原始运行、日志、精确比较和完整报告保留在本地忽略目录，不纳入提交：

- `experiments/results/agent_chain/agent_chain_v1_2_native_replay_001/`
- `experiments/results/agent_chain/agent_chain_v1_2_offline_001/`
- `experiments/results/agent_chain/agent_chain_v1_2_partial_offline_001/`
- `experiments/results/agent_chain/agent_chain_v1_2_acceptance/AGENT_CHAIN_V1_2_ACCEPTANCE_REPORT.md`

与修订规格不一致之处：**无**。待决问题：**无**。§5 的四项要求均已完成。
`.env` 与运行前 SHA-256 相同；没有改动或提交凭据，没有提交运行输出。
此前的 live 运行产物保留。本次真实模型调用数为 **0**，没有运行 live，没有合并到 main。
最终推送及工作区状态记录见交付回复和本地完整验收报告末尾。
