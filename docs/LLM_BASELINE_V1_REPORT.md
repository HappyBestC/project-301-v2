# LLM 直接排程对比实验 V1 实现报告

## 分支与提交

工作目录 `/home/private/project-301-v2-sa`，分支 `codex/llm-baseline-v1`，基于 `origin/codex/standard-answer-v1` 的 `14fbfb9`。推送到同名远程分支，不合并 main。

| 提交 | 内容 |
|---|---|
| `8b97a7d` | 指定开发文档原样导入，为本分支第一个提交 |
| `ed8baa0` | 首次审查的待决问题报告（本报告现已更新为最终交付报告） |
| `7b19971` | live_schedule、L0/L1 提示词与时效信息、资源编号提示及测试 |
| `46f8e0d` | 同口径比较器、只读不治疗对照重算和构造数据测试 |

最终报告提交可用 `git log -1 --format=%H -- docs/LLM_BASELINE_V1_REPORT.md` 查询。

## 实现结果

- `live_schedule` 使用 `TemplateTreatmentProvider` 和 `LLMSchedulingProvider`，仅支持本实验的 run_002，最多 3 轮请求。没有修改接受算法，直接复用现有 V1.2 实现，包括零冲突且未排入者全部为 `missing_parameters` 时提前接受，以及请求失败后的既有选择规则。
- L0 使用原提示词；L1 使用新文件 `resource_schedule_objective.md`，只有第一段目标说明替换为文档指定原文，其余字节保持一致。
- L1 时效信息通过共享 `TableStore`、`prepare_costs` 读取 typical 严重度的表，按个人 `H_i = 120 - arrival_time_min` 截取，使用文档的 0/10/20/30/45/60/90/120 时刻、一位小数。仅添加到模型请求副本；独立校验仍使用原始 context。表不可用时在创建运行和构造模型 provider 前拒绝。
- 六类编号冲突的反馈增加 `valid_resource_hints`，按任务地点及动作/照护要求列出真实人员、设备、位置 ID，不检查空闲、不做替代分配。只在新实验模式启用，保持现有三种模式行为不变。
- `manifest.json` 的 `parameters` 记录 `schedule_variant`、`prompt_sha256`、`tables_sha256`（逐文件哈希）；L0 无表时哈希集合为空。每轮保存模型 token 用量和模型请求耗时，失败请求也保存耗时。
- 新增 `python -m core301.standard_answer.compare`，输出 `comparison.csv`、`per_patient.csv`、`summary.md`。前者逐运行记录组别、接受轮次、覆盖人数、各轮冲突数、死亡/缺损、tokens 与模型耗时，并附三个对照；逐人表每人一行，将各运行和对照的排入状态、第一动作生效延迟、死亡和缺损并列为列；摘要给出分组通过率及均值/最小/最大。
- 无可接受排程的运行作为全员不治疗纳入分母，不剔除。缺损由共享 `deficit` 算法和指定健康参考计算。已接受排程的 Pulse 记录不完整时明确报错，不能把缺失数据当作零缺损或正常生存；缺失 token/耗时保持空值，不伪造为零。

## 对照核验

`--untreated-run` 默认指向用户指定原目录：

`/home/private/project-301-v2/experiments/results/agent_chain/agent_chain_run_002_live_003/`

仅只读读取原始逐人 `execution.json`、`samples.csv`，没有复制或修改该运行。重算后与 `runs/standard_answer/live003_baseline.json` 的逐人死亡、逐人缺损、总死亡、总缺损及健康参考 SHA-256 核对，不一致即报错。

| 对照 | Pulse 死亡数 | CO 缺损总和 L |
|---|---:|---:|
| live_003 全员不治疗 | 3 | 2329.2691139910867 |
| 标准答案 oracle G0 | 0 | 1383.0351165536842 |
| 标准答案 oracle G60 | 0 | 1188.2998996923375 |

这些是从已有 samples 重算的对照结果，不是本次新增模型实验结果。对照检查产物在忽略的 `runs/llm_baseline_v1_control_check/`，不提交。

## 测试结果

最终代码验证结果：

- `bash scripts/validate.sh`：退出码 0。首组 678 passed；全量非 integration 测试 1540 passed、28 deselected，耗时 387.57 秒。后续 demo、基线完整性、Pulse smoke、独立性检查全部通过。
- `python -m pytest -q tests -m integration -p no:cacheprovider`：28 passed、1540 deselected，耗时 400.29 秒，退出码 0。包含真实 native Pulse 检查；涉及模型接口的测试使用 mock，未连接真实模型。
- 合计 1568 项不同测试通过，其中新增 23 项。两组均只有 6 条现有依赖弃用警告。
- `git diff --check` 通过；§7 所有禁止路径与 `14fbfb9` 的差异为空；开发文档与指定远程原文一致。
- 两个 CLI 的 `--help` 均可正常运行；真实对照读取和重算通过。

复现命令：

```bash
source scripts/activate.sh
CORE301_VALIDATION_DIR=runs/llm_baseline_v1_validation_final bash scripts/validate.sh
python -m pytest -q tests -m integration -p no:cacheprovider \
  --junitxml=runs/llm_baseline_v1_validation_integration.xml
```


新增测试覆盖：模板处置无模型构造；L0/L1 假调度端到端；V1.2 提前接受/重试及全部冲突后全员不治疗；时效表逐项比对、插值、死亡截断、H_i 截取及副本隔离；提示词逐字节检查；六类编号提示、照护角色和反馈重试；mock SDK 的提示词/用量/耗时/失败审计；比较器汇总、逐人延迟、失败运行纳入、对照核验、基线不一致和不完整执行拒绝；CLI 通配符和只读对照参数。

未发起任何真实模型请求。测试和验证输出均未提交。

## §6 最终命令（用户执行）

以下命令会发起真实排程模型请求，本次没有执行。`llm_L0_1` 等运行 ID 必须尚未存在；已有目录会被拒绝覆盖。

```bash
cd /home/private/project-301-v2-sa && source scripts/activate.sh
for i in 1 2 3 4 5; do
  python -m core301.agent_chain.runner --mode live_schedule --schedule-variant L0 \
    --scenario run_002 --run-id llm_L0_$i
  python -m core301.agent_chain.runner --mode live_schedule --schedule-variant L1 \
    --scenario run_002 --tables runs/curve_probe_001/tables --run-id llm_L1_$i
done
python -m core301.standard_answer.compare --runs 'llm_L*' \
  --standard runs/standard_answer/sa_run002_oracle_G0 runs/standard_answer/sa_run002_oracle_G60 \
  --untreated-run /home/private/project-301-v2/experiments/results/agent_chain/agent_chain_run_002_live_003 \
  --out runs/llm_baseline_v1
```

运行默认写入 `experiments/results/agent_chain/llm_L*`；比较器的裸名称/通配符也在此根目录解析。`--runs` 还接受运行目录的绝对路径或带目录的相对路径。

共 10 次运行，每次 1–3 次排程请求，正常启动并完成时总计 10–30 次，处置模型请求为 0；请求失败不做 SDK 隐式重试。模型单请求 timeout 为 180 秒，以 30×180 秒计约 90 分钟请求等待预算，不是严格的端到端耗时上限。

历史 live_003/G0/G60 的最长单患者 native 推演耗时分别约 705/733/732 秒。现有执行器逐人并行，同等机器负载下可粗略按每轮 Pulse 约 12 分钟估算，10 轮串行约 2 小时，再加模型等待及调度/读写开销，建议预留约 2–4 小时；实际时间取决于模型延迟、CPU 并发和终止事件。本次没有为估计时间发起任何真实模型请求或重跑完整实验。

## 与原文不一致之处

1. 按用户后续澄清，以 V1.2 实现为准，保留文档 §2 转述漏写的 `missing_parameters` 提前接受例外，不新写接受逻辑。
2. 按用户后续要求新增 `--untreated-run`，默认读取原工作树指定目录，并核对历史基线 JSON。
3. §3.3 的编号提示仅用于新模式的 L0/L1，避免违反 §7 对既有 offline/native_replay/live 行为不变的要求。

开发文档保持原样。未修改 §7 禁止路径、原调度提示词、配置或数据集；没有合并 main，没有提交运行输出、`.env` 或凭据。真实 L0/L1 实验与模型优劣结论留给用户运行后产生。

## 待决问题

无。此前两项问题已由用户明确：接受规则直接复用 V1.2；不治疗对照使用指定原目录并只读重算核验。
