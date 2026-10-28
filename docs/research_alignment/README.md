# 301 V2 科研工程与研究材料一致性审查

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

**总体结论：PARTIAL。当前工程可以作为四份研究说明与 M1 资源模型的统一实现基础，但尚不能称为已经贯通、由真实 Agent 使用十五指标并完成十二动作调度—Pulse—十四规则—反馈决策的统一科研 Runtime。**

本轮实际读取四份 Markdown 正文、公式及展开的 AST 说明；没有以文件名或存在性代替实现核查。研究材料用于对照，正式协议与锁定配置仍是实现核验依据。

|研究部分|定义/受限实现|当前完整链路|主要依据|
|---|---|---|---|
|十类基础伤情|MATCHED：正式登记十类，部位、固定严重度、环境参数及动作与材料一致|PARTIAL：多入口；通用伤情合同仍保留历史候选分支，非所有候选档位都准入|[逐伤情核查](INJURY_ALIGNMENT.md)|
|五类固定复合伤|MATCHED：固定组成、AB 顺序、时间窗及原生适配一致；有既有受限 Pulse 验收记录|PARTIAL：M2-C 5/5 合同/资源预留不等于新版计划到 Pulse 的 5/5 闭环|[四层对照](INJURY_ALIGNMENT.md)|
|十二动作与 M1—M2-C|MATCHED：十二动作研究 COSTS 全覆盖，共享管理与调度共用账本|PARTIAL：真实资质/规格/时长仍未知，执行回执尚未统一桥接|[动作资源映射](ACTION_RESOURCE_ALIGNMENT.md)|
|十五指标|MATCHED：字段、单位、来源、分层与冻结档案一致|PARTIAL：ARCHIVE_VERIFIED / USER_ACCEPTANCE_PENDING / NOT_ACTIVATED 仍成立；实际 Treatment Provider 仍用旧合同|[观察合同核查](OBSERVATION_ALIGNMENT.md)|
|十四规则|MATCHED：内容与锁定 AST、三项 SHA 一致|PARTIAL：研究适配器与历史实验有评价证据，当前完整 Runtime 未调用；正式评分仍关闭|[规则逐条核查](EVALUATION_ALIGNMENT.md)|

## 明确差异与证据限制

1. **MISMATCH（文档解释）**：内出血历史验证报告将 05/06 CO 增量写成除以末窗 zero CO；锁定 AST 和用户材料明确除以共同治疗前 `B.CO`。本轮不改任一来源，也不能仅凭文字错误认定原生计算错。详见规则报告 D2。
2. **MISMATCH（若作为当前状态读取）**：规则汇总与发布 manifest 保留锁定时的“独立验证待完成/完成 0”快照；后续 `pulse_validation_09_v1` 报告已汇总十四条首轮 AST 输出：10 E、3 P、1 I。该快照不能作为当前实验进度台账；十四条有输出也不能替代全部严重度分支验收。
3. **PARTIAL（实际接口差异）**：旧 `CasualtyInput` 并非正式十类统一合同；旧观察器仍含 ICP、无新版 COHb/Na 字段；旧 Treatment Provider 输出八动作。均有明确历史边界，不能把它们称作当前完整 V2 合同。
4. **UNVERIFIED（本地复现）**：当前工程未包含大型 `independent_native_execution_driver_v1/native_campaigns/` 原始目录。既有报告可证明记录过哪些运行和异常；本轮不能独立复算这些原始轨迹。没有读取报告中指向原横向工程的绝对路径。
5. 血胸 09 的既有 I 与 E1 动作瞬间流率缺测相关；这是“缺测进入机制布尔失败”的解释缺口，不能宣称已证实治疗无效，也不能本轮改为 NOT_EVALUABLE。

## 报告导航

- [INJURY_ALIGNMENT.md](INJURY_ALIGNMENT.md)：十类及五类、患者与准入范围。
- [ACTION_RESOURCE_ALIGNMENT.md](ACTION_RESOURCE_ALIGNMENT.md)：全部十二动作、研究能力和资源语义。
- [OBSERVATION_ALIGNMENT.md](OBSERVATION_ALIGNMENT.md)：精确十五字段、真实消费方与隔离边界。
- [EVALUATION_ALIGNMENT.md](EVALUATION_ALIGNMENT.md)：十四规则 M/F、时间、对照、SHA 与入口。
- [PIPELINE_GAP_ANALYSIS.md](PIPELINE_GAP_ANALYSIS.md)：逐连接实现及 Mock/真实验证层次。
- [RECOMMENDED_NEXT_STEPS.md](RECOMMENDED_NEXT_STEPS.md)：后续最小任务，均未实施。

## 审查方式与保护

只读检查源代码调用、配置结构、档案记录、既有测试源码；重新计算冻结规则 SHA 和 canonical SHA。未重跑业务测试，未用测试数量推断新原生验证。迁移/清理的非原生测试见 [docs/RESEARCH_CLEANUP_REPORT.md](../../docs/RESEARCH_CLEANUP_REPORT.md)，其运行证据与本次静态核查分开。

审查前快照包含927个既有文件（排除虚拟环境及目录符号链接目标）；审查后逐个SHA核对，0修改、0缺失，仅新增本目录七份报告。业务代码、配置、Prompt、资源管理、观察契约、规则、Pulse 适配器均保持原字节。完成后停止，等待下一阶段确认。

## 本轮实际只读核验结果

|核验|结果|边界|
|---|---|---|
|正式十类JSON与restricted REGISTRY集合|10/10一致|注册集合，不是十次新原生运行|
|CompletePlan十二枚举与Catalog/COSTS|12/12一致|研究映射，不是临床需求确认|
|复合配置与冻结副本|5项内容相同，源文件SHA匹配|不创建CompositeCase|
|十五指标当前catalog与冻结metric_catalog.agent|逐项完全相同；15=5+10|仅导入常量，不初始化引擎/Provider|
|三条后续restricted准入门控|血胸/CO/低氧3/3证据SHA通过|其余七类走phase1入口，不适用此manifest|
|五条复合准入门控|5/5证据SHA通过|仅调用verify_admission，不执行Pulse|
|规则与canonical参数/定义SHA|三项匹配|未运行疗效实验|
|报告本地Markdown链接|全部目标存在|历史文件正文中的旧链接不因此获验证|

准入只读核验包含新工程指向的独立 `/home/private/pulse-4.3.2-301-runtime` 依赖哈希；未访问原横向工程。一次将phase1伤情传入后续三类专用准入函数的探查被原门控拒绝；按research_router实际分派范围核查后3/3通过，没有将该范围拒绝当作实现缺陷或原生实验失败。
