# 分诊器 V1 实施报告

状态：分诊核心、离线 CLI、所有链路模式的分诊记录及 L2 调度变体已完成，全部测试与验证通过。

## 分支与提交

- 工作目录：`/home/private/project-301-v2-triage`。
- 分支：`codex/triage-v1`，基于 `origin/codex/llm-baseline-v1` 的 `e2cc253`。
- 交付到同名远程分支 `origin/codex/triage-v1`，不合并 main。

| 提交 | 内容 |
|---|---|
| `f851c57` | 通过指定 checkout 命令原样取入开发文档，是基线之后的首个提交 |
| `40cc33f` | 后台伤口描述、可观察输入分诊规则、离线 CLI 和规则测试 |
| `b5b57cd` | 所有 Agent 链路模式写入分诊状态与文件；L2 请求副本转换及隔离测试 |
| `17eee01` | 启用 L2 命令行与新提示词；模拟 SDK 三轮调度、提示词字节及 CLI 测试 |

报告自身的提交可用 `git log -1 --format=%H -- docs/TRIAGE_V1_REPORT.md` 查询。

## 实现与输入隔离

- `src/core301/triage/wounds.py` 是后台投影：按文档处理十类伤情、四肢和胸部左右侧、五档严重度。不可见伤口不读取严重度，`grade` 为 `null`；不支持的外出血 compartment 报错。
- `src/core301/triage/rules.py` 的分诊入口为 `triage(wounds, HR, RR, GCS=15)`，只接收这四项，不读取文件、伤情规格或严重度。按照 §3 顺序命中即停，不做取整或阈值修正。生命体征不可用、缺失或不是有限数值时失败，不使用默认生命体征。
- `src/core301/triage/service.py` 在宿主侧完成后台描述生成和快照读取，再将描述、HR、RR 交给规则函数；原始伤情规格不进入规则函数、处置请求或调度请求。
- `load_scenario` 中紧接 `load_cases` 的既有校验执行分诊，在处置之前把结果写入状态的 `triage` 字段及运行目录的 `triage.json`。文件结构为 `patients` 逐人列表与 `summary` 四色人数，亦纳入既有文件哈希清单。保留原图节点与校验算法。
- 处置 Agent 输入保持不变。L0、L1 的调度请求保持原样；L2 输入转换只在模型副本中删除每人的 `observation`、增加 `triage_tag`，不传入原因、分诊 inputs 或 urgency。原始校验器 context 不变。
- `live_schedule --schedule-variant L2` 使用模板处置及新提示词，不要求反应表。沿用原重试/接受机制及 `manifest.json` 的组别、提示词 SHA-256 审计；未新增分配算法或改变校验器。
- CLI 在当前工作目录写入 `triage.json`，逐人打印伤口描述、原始 HR/RR、分级与原因。只读取保存的场景快照，不初始化 Pulse，也不构造模型请求。

## 测试结果

- L2 接入完成后的分诊、L0/L1 和 L2 定向回归：118 passed，17.86 秒；含模拟 SDK 三轮调度及提示词逐字节校验。
- 最终代码的 `bash scripts/validate.sh`：退出码 0，首组 678 passed；全量 1639 passed、28 deselected，399.11 秒。后续 demo、基线完整性、Pulse smoke、独立性检查全部通过；有 6 条既有依赖弃用警告。
- Native integration：28 passed、1639 deselected，332.41 秒，退出码 0；6 条既有依赖弃用警告。运行真实 native Pulse 检查，所有模型接口均使用 mock。
- 最终代码合计 1667 项不同测试全部通过，其中新增 99 项。没有发起真实模型请求。
- `git diff --check` 通过；首提交仅含指定文档、禁止路径无差异、所有已有提示词字节不变及环境链接不受 Git 跟踪的检查通过。本地审计记录：`runs/triage_v1/final_source_audit.json`。

新增测试包括所有伤情映射与可见程度、隐藏伤口禁止读取严重度、纯分诊函数签名、七步规则及顺序、严格边界（含 RR=12.048）、步行条件、缺失/不可用生命体征、run_002 逐人验收、CLI 不调用模型/Pulse、四种模式在处置之前记录分诊、处置和 L0 输入等值、L2 重试请求副本与原始校验上下文隔离、按 patient_id 关联排除后的患者。

测试中的 `DEFAULT_DELAYED` 使用合成的非裂伤腿部可见描述，单独覆盖最后一条规则；未增加任何后台伤情映射。现有 V1 场景不会因此产生新伤情。

本次保留的测试输出位于当前 worktree 的 `runs/triage_v1/` 下，不提交；`TMPDIR` 也指向该目录，既有测试显式创建的临时运行仍位于当前 worktree。完整验证以较低 CPU 优先级执行。

最终验证复现命令：

```bash
cd /home/private/project-301-v2-triage
source scripts/activate.sh
CORE301_VALIDATION_DIR=runs/triage_v1/validation_final nice -n 10 bash scripts/validate.sh
export TMPDIR="$PWD/runs/triage_v1/validation_final/tmp"
nice -n 10 python -m pytest -q tests -m integration -p no:cacheprovider \
  --junitxml=runs/triage_v1/integration.xml
```

## run_002 验收

逐人结果全部匹配 §6.6：红 7、黄 0、绿 9、黑 0。表中 HR/RR 使用快照原值，规则计算未做取整。

| 伤员 | HR | RR | 分级 | reason_code |
|---|---:|---:|---|---|
| P01 | 75.3228860921755 | 12.0481927710843 | red | CATASTROPHIC_HEMORRHAGE |
| P02 | 72.43963619176705 | 12.0481927710843 | green | AMBULATORY |
| P03 | 72.1637345691154 | 14.851485148514843 | green | AMBULATORY |
| P04 | 70.58063864826099 | 12.345679012345645 | green | AMBULATORY |
| P05 | 117.05831083797636 | 13.888888888888868 | red | TACHYCARDIA |
| P06 | 72.43963619176705 | 12.0481927710843 | green | AMBULATORY |
| P07 | 72.53895298710164 | 12.29508196721308 | green | AMBULATORY |
| P08 | 75.41573595883096 | 12.552301255230095 | green | AMBULATORY |
| P09 | 75.3228860921755 | 12.0481927710843 | red | CATASTROPHIC_HEMORRHAGE |
| P10 | 116.77217799274908 | 14.354066985645918 | red | TACHYCARDIA |
| P11 | 117.05831083797636 | 13.888888888888868 | red | TACHYCARDIA |
| P12 | 72.41262269236756 | 12.145748987854216 | green | AMBULATORY |
| P13 | 72.1637345691154 | 14.851485148514843 | green | AMBULATORY |
| P14 | 144.93123339097127 | 12.244897959183639 | red | TACHYCARDIA |
| P15 | 75.3228860921755 | 12.0481927710843 | red | CATASTROPHIC_HEMORRHAGE |
| P16 | 72.53895298710164 | 12.29508196721308 | green | AMBULATORY |

包含每名患者完整伤口描述和 inputs 的本地产物：`runs/triage_v1/run_002/triage.json`；逐人打印记录：同目录 `triage_stdout.txt`。

复现离线验收：

```bash
cd /home/private/project-301-v2-triage
source scripts/activate.sh
mkdir -p runs/triage_v1/run_002
cd runs/triage_v1/run_002
python -m core301.triage.cli --scenario run_002
```

## L2 提示词替换对照

按用户确认的精确范围，仅替换以下一句；替换前后逐字列出。

替换前：

> 每名伤员的 `urgency` 给出了 Pulse 测得的时效信息：`effective_after_injury_min` 的键是"方案第一个动作的操作结束时刻减去受伤时刻"（分钟），值是该时刻生效时的死亡与否和 CO 缺损；`untreated` 是不处置的结局。

替换后：

> 每名伤员的 `triage_tag` 是分诊器给出的分级：`red` 为立即处置（有生命危险，及时处置可以救活），`yellow` 为延迟处置（需要处置，暂无生命危险），`green` 为轻伤（可以最后处置），`black` 为已无呼吸（不分配救治资源）。资源不足时，按分级从高到低优先安排。

新文件为 `src/core301/dispatch/prompts/resource_schedule_triage.md`。除上述替换外，与 `resource_schedule_objective.md` 逐字节相同（含换行）。前一句“排入人数本身不是目标：资源不足时，优先保证会因延误而死亡的伤员。”完整保留。测试使用字节替换等式验证整份文件，而非只比较目标段。

新提示词 SHA-256：`0b64c635483f670d22bb3af00b575c4a557cb70043348dbf05548358d42fca41`。

## 与开发文档不一致之处

- §7 中旧工作目录 `/home/private/project-301-v2-sa` 已被用户的明确指令覆盖；所有修改只在 triage worktree 中进行。
- §4.2 的“两句”经用户明确更正为笔误：仅替换从“每名伤员的 `urgency` 给出了”至“`untreated` 是不处置的结局。”这一句（含句号）；前一句“排入人数本身不是目标：资源不足时，优先保证会因延误而死亡的伤员。”逐字保留。

开发文档保持原样，SHA-256 为 `2977b6536cd6425dae89cb734b07168ea3a4b5255fdbb38a7555755521f0860c`。所有已有提示词逐字节保持不变；§7 禁止路径相对基线无修改。没有提交运行输出、环境链接、`.env` 或凭据，未合并 main。没有向真实模型发起请求，也没有修改、切换、提交其他两个工作目录或停止其中实验进程。

## 待决问题

无。提示词替换范围的歧义已由用户明确答复，按该答复实施；开发文档原文件未改写。
