# 标准答案 CP-SAT V1 实现报告

分支：`codex/standard-answer-v1`。工作目录：`/home/private/project-301-v2-sa`。

实现了离线求解、三阶段字典序目标、排程导出、逐人加入诊断以及独立 native Pulse 复核。
真实反应表尚未满足 §10 的完整性要求，因此本报告不宣称已取得真实标准答案或已完成真实排程的 Pulse 一致性验收。

## 1. 提交

- `2e084ca`：提取共享 CO 缺损算法，固定 OR-Tools 及依赖，隔离 worktree 依赖环境。
- `7c3d68e`：反应表、严重度变体、CP-SAT 模型、三阶段目标、排程导出、未排入者诊断。
- `2c9911c`：补充运输、设备周转、库存和未排入结果的约束覆盖。
- `23c2378`：命令行、Pulse 复核、诊断边界保护和 worktree 验收脚本。
- 本报告与完整 120 分钟窗口的非单调报告补充单独提交；该报告提交的哈希见最终交付消息。

没有合并到 `main`；未提交运行输出、依赖安装目录、符号链接或凭据。

## 2. 实现与用户补充决定

`src/core301/standard_answer/` 包含 `tables.py`、`scenario.py`、`model.py`、`solve.py`、`diagnose.py`、
`export.py`、`deficit.py`、`verify.py`、`cli.py`。

场景加载使用 `api.load_config`、`api.load_cases`、`api.build_input`；所有动作要求使用
`api.requirement(..., access_mode='new', mode='start')`。没有复制动作耗时、角色、设备、耗材或护理规则。
方案、车辆、目的地、动作地点、动作时刻、人员、设备、空间、支持床位和护理人员都由模型选择。

按本次对话补充的决定实现了以下行为：

1. 未测量 d 的死亡时刻与死亡判定取自同一个不早于 d 的有效测量点；`prediction.json` 记录 `interpolated`。
   对插值伤员，`comparison.json` 记录死亡时刻差异，但不据此判定不一致；死亡与否和 CO 缺损仍按原判据检查。
2. 环境变体使用 `environment_gases`；CO 暴露只接受 CarbonMonoxide，低氧只接受 Oxygen。
   严格检查用户指定的测量档位，固定 CO2=0.0004，并重算 Nitrogen；低氧的 CO 保持 0。
3. 新增阶段三：固定阶段二实际取得的死亡数、CO 缺损，最大化排入人数。保留每阶段状态、目标、界和间隙。
   第一阶段只有 `OPTIMAL` 才将 `deaths_optimality_proven` 标为 true；三阶段都为 `OPTIMAL` 才声明字典序最优性已证明。
4. 对未排入者固定其他伤员全部决策，检查加入可行性；依次检查单类放宽、全部放宽、按指定顺序累加、逐类删除。
   资源类别顺序为车辆、人员、设备、空间、库存；得到的是不能再删类别的最小组合。
   虚拟资源只用于诊断，映射回同类型、同地点的原资源 ID；车辆按同类型、同初始位置映射。
   车辆复制不自动提供额外人员、设备、空间或库存；相应类别需单独放宽。研究止血能力随设备类别复制。
5. 全部类别放宽仍不可行，导出 `time_window_insufficient`。能加入但会使前两级目标变差时，
   保存 `solve.json` 中的待决问题并停止导出。能加入且目标不差时，以该可行解继续求解，不填写虚假的资源瓶颈。

初始加入启发式和完整可行解 hint 只用于提供求解起点；正式目标仍是上述三阶段。
为控制大型可选区间模型的预处理开销，关闭 OR-Tools probing 和 symmetry 两个预处理启发式，参数写入 `solve.json`。
没有放宽正式排程的约束。

## 3. 约束覆盖

| 规则组 | 实现与检查 |
| --- | --- |
| 转运 | 单人最多一趟；AddCircuit 接续车辆位置；全部运输阶段按配置相加；车辆时段、人员、担架、可用时刻、伤员到达与规划期 |
| 动作与依赖 | 选中方案每个动作恰好一次；全程地点一致；start/new；时长、depends_on、动作类型及伤情前置；模板偏移与 G |
| 人员 | 按能力匹配独立人员；输血通路与主操作分阶段；人员地点、状态、可用时刻和绑定伤员 |
| 设备与空间 | 精确设备类型、设备周转、持续占用；支持床位；胸管必须有支持床位；同伤员不得占两个位置；同空间相邻动作空档占用 |
| 护理 | 按周期生成所有完整时段；转运中与送达后按实际地点分配；不漏护理、不中途跨地点 |
| 互斥 | 人员、设备、空间、车辆和研究止血能力；复用同伤员空间及本趟车辆人员例外；初始占用 |
| 库存 | 按地点扣减；新通路耗材；盐水、血液按完整 500 mL 承诺；氧气按速率与持续时间；机械通气氧气按校验器排除 |
| 结果 | 每人恰好一条；未排入者无任务；原因、实际诊断资源 ID 和考虑过的全部方案；demonstration_only=true |

在 §4 的明示规则之外，还覆盖了校验器的 `RESOURCE_UNAVAILABLE`、`RESOURCE_BOUND`、初始占用等检查。
`unchecked` 保留在 `validation.json`，未把“零冲突”解释为临床适应证已确认。

空间互斥对当前线性模板采用等价的 NoOverlap 表达，车上担架按同伤员的占用并集计算；
存在初始占用或非末尾持续动作时使用保留同伤员例外的逐对约束。

## 4. 测试

| 检查 | 结果 |
| --- | --- |
| 审查后复跑：`CORE301_VALIDATION_DIR=runs/standard_answer/validation_review_phase2 bash scripts/validate.sh` | 退出码 0；恢复原列表后的 M2 基线 678 passed；全量非集成 1517 passed、28 deselected |
| 历史运行：`CORE301_VALIDATION_DIR=runs/standard_answer/validation_final bash scripts/validate.sh` | 退出码 0；误替换测试列表后的 M2 基线 685 passed；全量非集成 1505 passed、28 deselected；原列表复跑结果见下文审查更正 |
| 初次全量检查后增加的约束边界覆盖 | `tests/standard_answer/test_constraints.py`：63 passed（含新增 12 项） |
| 全部 native 集成测试 | 28 passed、1502 deselected，941.22 秒 |
| 最终标准答案专项测试 | 94 passed，211.67 秒；之后全窗口非单调报告补充经表测试再次验证 |
| 冻结研究文件核验 | 858 个文件，errors=[] |
| demo 资源守恒检查 | 128 次检查通过 |
| Pulse smoke / 独立性检查 | 通过；隔离进程从当前 worktree 导入，旧项目读取策略 DENIED |

全量脚本与新增约束覆盖的计数有重叠，不应相加当作一次测试运行的总数。
native 集成测试只执行既有测试中的 Pulse 路径，没有发起 live 模型请求。
日志、JUnit XML 和完整假表运行证据位于 `runs/standard_answer/`，未提交。

- 小场景枚举 3 名伤员、1 辆车的全部服务子集、顺序和方案组合，包含车上处置；与 CP-SAT 三阶段目标一致。
- 手工表覆盖映射、H_i 截取、线性插值、保守死亡判定、缺失行、缺少端点时拒绝外推，以及死亡恢复的非单调记录。
- 共享 CO 算法与提取前代码和 `curve_probe_001` 已有 native 输出逐点回归一致。
- 违反约束的排程交给原校验器确认冲突；对时间、依赖、能力、占用、库存等决策增加相应强制条件，确认模型不可行。
- `run_002` 假表端到端测试禁止调用 Pulse/模型；变体 typical 模式使用典型表优化、真实表评价；缺少真实表时退出。
- verify 测试检查所有伤员均传给 native bridge 接口、真实严重度输入、时钟换算和插值死亡时刻例外。

撤回原先“`tests/v2/test_phase2_gates.py` 不存在”的判断，以及据此将它替换成 `test_phase2_audit.py` 的改动。
该文件一直存在，测试列表已恢复原来的 `test_phase2_gates.py`；核查原因和复跑结果见下文审查更正。
脚本支持 `CORE301_VALIDATION_DIR`；独立性检查从当前 worktree 加载模块，避免共享 `.venv` 的 editable 安装指向原目录。
这两项仅调整验证入口，没有修改 Agent 链路的行为。

### 审查更正：恢复原始 M2 测试列表

审查后分别执行 `git ls-tree main tests/v2/test_phase2_gates.py`、
`git ls-tree codex/standard-answer-v1 tests/v2/test_phase2_gates.py` 和
`git ls-tree 9e6e191 tests/v2/test_phase2_gates.py`，三处均返回同一 blob：
`c4d1e2eebb2793fdf535014e5b7036b8046e34b5`。工作树文件也实际存在；没有发现忽略规则将它排除。

当初判断错误的原因是：我在较长、部分被截断的批量文件清单中没有注意到该路径，便将“没有看到”误当成“不存在”。
当时没有针对该文件执行 `ls`、`test -f` 或 `git ls-tree`，也没有先运行原测试列表取得文件缺失的错误证据。
这是我的核查疏漏，测试替换没有依据；并非仓库缺少该文件，也不是测试文件更名。

本次仅将 M2 基线命令中的 `test_phase2_audit.py` 恢复为 `test_phase2_gates.py`，
保留 `CORE301_VALIDATION_DIR`、临时目录、输出重定向和 worktree 独立性检查等其他改动。
随后完整复跑：

```bash
cd /home/private/project-301-v2-sa
source scripts/activate.sh
CORE301_VALIDATION_DIR=runs/standard_answer/validation_review_phase2 bash scripts/validate.sh
```

复跑已完整结束，脚本退出码 **0**：

| 检查 | 本次结果 |
| --- | --- |
| M2 原始测试列表 | 678 passed，16.97 秒；JUnit 确认包含 13 个 `test_phase2_gates` 用例，不包含 `test_phase2_audit` |
| 全量非集成测试 | 1517 passed、28 deselected、6 个既有弃用警告，536.72 秒 |
| 冻结研究文件 | 858 个文件，errors=[] |
| demo 资源守恒 | 128 次检查通过 |
| Pulse smoke | 通过，treatment_actions=0、advanced_steps=0 |
| worktree 独立性 | 通过，isolated=1、old_tree_open_policy=DENIED |

日志：`runs/standard_answer/validate_review_phase2.log`；JUnit XML 和后续检查结果：
`runs/standard_answer/validation_review_phase2/`。这些运行产物不提交。

## 5. §10 验收结果

### 真实表就绪性

检查 `runs/curve_probe_001/tables/`：run_002 的 10 个伤情组共需 12 张方案表。
共享 CSV 仍为旧汇总，完整可用为 **0/12**：全部缺少可覆盖 d=0 的有效测量点/插值端点。
进一步只读检查原始测量文件发现，**12 个方案的 25 个粗网格点均已齐全**；但按照原 `curve_probe.py`
的 refine 规则仍缺 **68 个一分钟补点**：外出血+补液 32 个、外出血+输血 32 个、开放性气胸敷料 4 个。
因此真实反应表的“粗网格加转换处补点”尚未完成，§10 仍待补点与正式汇总。
没有生成替代表、外推缺失端点或运行测量/汇总命令，也没有改变正在测量的目录。
本地证据：`runs/standard_answer/acceptance_readiness.json`，包含逐表原因、原始粗网格/补点检查和全部现有 CSV 的 SHA-256。

因此真实 `solve --table-mode oracle`、对应的 native `verify` 和逐人一致性比较尚未执行。
测量完成后可运行：

```bash
cd /home/private/project-301-v2-sa
source scripts/activate.sh
python -m core301.standard_answer.cli solve --scenario run_002 \
  --tables runs/curve_probe_001/tables --table-mode oracle --run-id sa_run002_oracle_001
python -m core301.standard_answer.cli verify --run-id sa_run002_oracle_001
```

`solve` 保存表的快照与 SHA-256，以及 context/真实 patient_specs；verify 的临时 patient_specs 写在本次输出目录内，
不会写入 `dataset_v1`。正常输出包含规范要求的 schedule、validation、prediction、solve、pulse 和 comparison。

### 假表开发运行

`runs/standard_answer/fake_run002_005/` 使用手工常数代价表，仅验证工程链路。
参数：每阶段 60 秒、2 workers、seed=0、G=0；一次加入改进后得到以下最终阶段结果：

| 阶段 | 状态 | 目标 | 界 | 求解时间 |
| --- | --- | ---: | ---: | ---: |
| 死亡数 | OPTIMAL | 0 | 0 | 3.878 s |
| deficit10 | FEASIBLE | 9800 | 0 | 60.324 s |
| 排入人数 | FEASIBLE | 7 | 16 | 60.927 s |

16 人全部有结果，排入 7 人，未排入 9 人；原校验器冲突数 **0**。
9 名未排入者均有固定决策加入检查、资源放宽过程与瓶颈资源列表。
第二、三阶段未证明最优；以上为假表可行解，不能作为真实生理结局或真实标准答案。

### 与 live_003 对比

只读检查了原目录 `experiments/results/agent_chain/agent_chain_run_002_live_003/` 的历史输出，未重跑该链路。

| 指标 | live_003 历史实测 | 本次真实标准答案 |
| --- | ---: | --- |
| 实际推演人数 | 16 | 待真实表完成 |
| 已接受治疗人数 | 0 | 待真实表完成 |
| 死亡数 | 3（P01、P09、P15） | 待真实表完成 |
| CO 缺损总和 | 2329.2691139910867 L | 待真实表完成 |

CO 缺损由历史 samples.csv、同一健康参考和共享算法重新计算，按各伤员 H_i 截取；
死亡时刻分别约为全局 73.012、83.012、93.012 分钟。未治疗反应表按 H_i 截取得到同样结果。
本地重算证据：`runs/standard_answer/live003_baseline.json`。没有把旧的 ∫CO 总和当作 CO 缺损。

## 6. 环境、边界与待决问题

OR-Tools 固定为 `9.10.4067`，`pyproject.toml` 和 `requirements.lock.txt` 均已更新。
该版本的 [PyPI 依赖元数据](https://pypi.org/pypi/ortools/9.10.4067/json) 允许现有 protobuf 5.29.2；
没有修改共享 `.venv` 中的 protobuf 或任何其他包。新增依赖安装在本 worktree 的
`runs/standard_answer/_deps/`，`scripts/activate.sh` 在该目录存在时加载它。

所有文件修改、测试输出和临时文件均在指定 worktree。原目录测量脚本、运行输出未修改，测量进程未暂停或终止；main 仍为 `c94ee6d`。
未修改规范 §11 禁止路径，未发起任何真实 LLM 请求；Pulse 仅用于测试，真实 verify 尚未触发。

与原文不同之处是用户在对话中明确批准的阶段三、插值死亡时刻复核规则、环境变体格式及未排入者诊断规则。
当前 V1 范围内未发现需保留的未建模 conflict 规则。

待决问题：

1. `--max-followup-gap` 的最终取值仍待用户根据 gapcheck 决定；默认值和本次测试取值均为 **0**。
2. 真实表完成后须补跑 §10，才能报告真实标准答案与逐人 Pulse 一致性。目前不能判定真实表下是否出现
   “可加入但会使前两级目标变差”；一旦出现，程序会停止导出并在 `solve.json` 中列出待决伤员。

其余先前未定义的死亡时刻、环境覆盖和诊断边界，均已由本次对话中的用户答复解决。
