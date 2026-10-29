# LLM 直接排程对比实验 V1 执行报告

## 状态

实现暂停，尚未完成实验功能。遵循开发文档开头和用户指示：需要设计决定时停下来记入“待决问题”，不自行决定。没有发起任何真实模型请求，没有运行真实实验。

## 分支与提交

- 工作目录：`/home/private/project-301-v2-sa`。
- 已执行 `git fetch origin`，从 `origin/codex/standard-answer-v1`（`14fbfb9`）创建 `codex/llm-baseline-v1`。
- 首个提交：`8b97a7d docs: add LLM baseline v1 development specification`。开发文档通过指定的 `git checkout origin/claude/llm-baseline-spec -- docs/LLM_BASELINE_V1_DEV_SPEC.md` 取出，未改写。
- 第二个提交为本报告，主题为 `docs: report LLM baseline specification blockers`；提交 ID 可用 `git log -1 --format=%H -- docs/LLM_BASELINE_V1_REPORT.md` 查询。
- 交付分支为 `origin/codex/llm-baseline-v1`，不合并 main。
- 未修改任何实现或 §7 禁止路径，未提交运行输出、环境文件或凭据。

## 待决问题

### 1. 部分排入且仅缺参数时，是否提前接受（阻塞接受规则实现）

§2 写明“有 0 冲突全员排入则立即接受，否则取 0 冲突轮次中排入最多的一轮”，同时要求“接受规则沿用 V1.2”；§3.4 又要求接受规则与现有 `live` 完全相同。

但 `src/core301/agent_chain/nodes.py` 的 `acceptable()` 在零冲突且全部未排入原因均为 `missing_parameters` 时返回真；`Nodes.validate()` 会据此立即接受部分排程，`graph.after_validation()` 随即结束请求循环。现有测试 `tests/agent_chain/test_graph.py::test_missing_parameters_accept_immediately_other_omissions_wait_for_limit` 明确要求这种情况仅请求一次。

需要明确：新模式保留该提前接受例外，还是严格执行 §2 的“全员排入才立即接受”，仅对新模式取消该例外？两者会改变模型反馈轮数和最终选中的排程，不能自行选择。现有 `live` 行为必须保持不变。

### 2. `live_003` 对照数据位置（阻塞真实对照验证）

§4 指定不治疗对照 `live_003`，但本工作树的 `runs/` 和 `experiments/` 下未找到该运行的 `manifest.json`、`summary.json` 或 `outcomes.json`，默认位置 `experiments/results/agent_chain/live_003` 也不存在。

需要提供该运行目录及其逐人 Pulse 样本，或明确另一个允许使用的对照来源。本次没有自行生成替代对照，也没有把反应表不治疗行当作指定的真实运行。

## 测试结果

已运行：

```bash
source scripts/activate.sh
CORE301_VALIDATION_DIR=runs/llm_baseline_v1_validation bash scripts/validate.sh
```

脚本退出码 0：首组 678 passed；全部非 integration 测试 1517 passed、28 deselected、6 warnings（367.97 秒）。警告为现有依赖弃用提示。脚本后续 demo、基线完整性、Pulse smoke 和独立性检查也全部完成。integration 标记测试未执行，不能称为所有标记测试均已通过。

现有测试明确覆盖了待决问题 1 中的提前接受规则；未修改测试期望。

本次未新增功能，因此 §5 的新功能测试尚未实现，不能声称开发验收通过。测试输出仅留在忽略的 `runs/llm_baseline_v1_validation/`，不提交。

## §6 命令与请求数、耗时

当前没有可执行的最终实验命令：`live_schedule`、`--schedule-variant`、`--tables` 和 compare 模块尚未实现。下列保留文档的待实现接口，**当前不要执行**；待问题明确并实现验收后才能作为最终命令：

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

设计目标是 10 次运行，每次最多 3 次排程请求，正常完成情况下共 10–30 次；处置模型请求为 0。本次实际真实模型请求为 0。

现有调度 provider 的单请求 timeout 为 180 秒、SDK 重试为 0。30 次请求各按 180 秒预算约 90 分钟，仅用于估算请求等待预算，不是端到端耗时保证；还要加 10 次全员 native Pulse 推演、文件读写和比较耗时。没有真实模型时延测量，不能提供有依据的实际总耗时预测。

## 与开发文档不一致之处

本次仅完成分支建立、开发文档首个提交、实现前审查和报告；§3 功能、§4 比较器及 §5 新增测试均未交付。原因是上述接受规则需要明确，已按用户“停下来”要求停止实现。没有擅自改变实验口径。基线验证结果不代表新实验功能通过验收。
