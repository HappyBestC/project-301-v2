# 与锁定JSON的一致性检查

结果：**通过**。仅生成Markdown说明与本报告，不修改规则、阈值或已锁定归档，不运行Pulse。

自动执行检查共123项，全部通过。源JSON及锁定副本SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。参数canonical SHA：`ed3ed8ae24f4da9f887202318c372f60a39ff95d3b9ffecf91b7870819c090f7`。

自动检查范围：解析唯一JSON，按原AST逐节点保留布尔结构、分支、指标/窗口、参数引用及数值，生成每条可折叠研发核对区；再从最终文本检查14行总表、14个详细章节、阈值/事实/单位/时间及归档SHA。总表和通俗说明另逐条对照原AST审核。**自动文本检查不是任意自然语言的语义证明，也不是疗效或医学验证。** 本次没有发现未解决的表述歧义。

关键消歧：07主判定不添加健康距离门槛；08两指标分别处理零距离；09保留资格范围/双模式/E1时间可用性；10分别保留异常基线恢复和正常基线维持；12保留所有AND及健康上端点；13/14环境检查全POST。

| 检查项 | 结果 | 依据/说明 |
| -- | -- | -- |
| 源规则及锁定副本SHA | PASS | 6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f |
| 总表14条无遗漏/重复 | PASS | 14/14，01–14各一行 |
| 详细说明14条 | PASS | 14/14，统一九项模板及通俗理解 |
| 二级/三级及等级谓词 | PASS | 01/04不适用P；其余P为M且非F，I仅可评价而非M |
| V2E-01 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-01 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-01 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-01 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-01单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-01机制与前提 | PASS | authorization_valid；execution_valid；scope_valid；single_source_identity_valid |
| V2E-01实际引用阈值 | PASS | 2个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-02 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-02 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-02 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-02 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-02单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-02机制与前提 | PASS | authorization_valid；execution_valid；matched_zero_valid；scope_valid；source_controlled_context_valid；support_exclusivity_valid |
| V2E-02实际引用阈值 | PASS | 3个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-03 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-03 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-03 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-03 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-03单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-03机制与前提 | PASS | authorization_valid；execution_valid；matched_zero_valid；scope_valid；source_controlled_context_valid；support_exclusivity_valid |
| V2E-03实际引用阈值 | PASS | 3个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-04 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-04 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-04 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-04 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-04单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-04机制与前提 | PASS | authorization_valid；execution_valid；scope_valid；single_source_identity_valid |
| V2E-04实际引用阈值 | PASS | 3个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-05 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-05 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-05 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-05 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-05单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-05机制与前提 | PASS | authorization_valid；execution_valid；matched_zero_valid；scope_valid；source_controlled_context_valid；support_exclusivity_valid |
| V2E-05实际引用阈值 | PASS | 3个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-06 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-06 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-06 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-06 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-06单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-06机制与前提 | PASS | authorization_valid；execution_valid；matched_zero_valid；scope_valid；source_controlled_context_valid；support_exclusivity_valid |
| V2E-06实际引用阈值 | PASS | 3个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-07 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-07 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-07 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-07 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-07单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-07机制与前提 | PASS | authorization_valid；endpoint_chest_seal_proxy；execution_valid；scope_valid；side_valid |
| V2E-07实际引用阈值 | PASS | 7个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-08 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-08 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-08 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-08 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-08单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-08机制与前提 | PASS | authorization_valid；endpoint_needle_patent_proxy；execution_valid；scope_valid；side_valid |
| V2E-08实际引用阈值 | PASS | 10个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-09 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-09 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-09 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-09 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-09单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-09机制与前提 | PASS | E1_complete；authorization_valid；execution_valid；native_auto_stop_confirmed；scope_valid；side_valid |
| V2E-09实际引用阈值 | PASS | 15个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-10 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-10 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-10 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-10 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-10单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-10机制与前提 | PASS | authorization_valid；execution_valid；patient_PBW_kg；scope_valid；ventilation_support_confirmed |
| V2E-10实际引用阈值 | PASS | 8个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-11 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-11 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-11 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-11 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-11单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-11机制与前提 | PASS | authorization_valid；execution_valid；oxygen_support_confirmed；scope_valid |
| V2E-11实际引用阈值 | PASS | 4个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-12 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-12 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-12 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-12 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-12单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-12机制与前提 | PASS | authorization_valid；execution_valid；matched_healthy_total_fluid_mL；matched_healthy_total_fluid_upper_mL；scope_valid |
| V2E-12实际引用阈值 | PASS | 10个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-13 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-13 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-13 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-13 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-13单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-13机制与前提 | PASS | authorization_valid；execution_valid；scope_valid |
| V2E-13实际引用阈值 | PASS | 5个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-14 prerequisites逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-14 eligibility逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-14 minimum逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-14 complete逐节点转写 | PASS | 保留AND/OR/if、严格不等号、窗口和原参数引用 |
| V2E-14单位和时窗 | PASS | 指标单位及固定终点/末60秒保留 |
| V2E-14机制与前提 | PASS | authorization_valid；execution_valid；scope_valid；target_events_inactive_W |
| V2E-14实际引用阈值 | PASS | 6个判定引用；不将注册表闲置/辅助槽位加入疗效门槛 |
| V2E-01等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-02等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-03等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-04等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-05等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-06等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-07等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-08等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-09等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-10等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-11等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-12等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-13等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| V2E-14等级完整谓词 | PASS | E/P/I/NOT_EVALUABLE与源JSON逐字段核对 |
| 不可评价与安全独立 | PASS | 保留缺测非I、安全不被E抵消 |
| 版本验证状态 | PASS | 区分工程/历史/Mock与尚未执行的独立原生验证 |
| 源参数未变 | PASS | 参数canonical SHA ed3ed8ae24f4da9f887202318c372f60a39ff95d3b9ffecf91b7870819c090f7 |
| 源文件未变 | PASS | 生成前后再次核验 |
| 易错比较语义 | PASS | 支持增量zero、07 Control、13/14全POST环境条件 |
| 恢复/维持及零距离分支 | PASS | 08零分母不补epsilon；09模式资格；10维持比例80%/100% |
| 锁定归档未改 | PASS | 1008项SHA全部一致 |

## 文件与范围

- 汇总表：`Treatment_Effect_Rules_V1.0_最终规则汇总表.md`
- 汇总表SHA-256：`fcb6f4766d2501db58220b562ef0bd97139cd4af0eed446df60065b7d6724d90`
- 原始规则、AST、参数及只读归档：未变。
- 离线测试382项：引用锁定版已完成记录，本次未重复运行全量回归，也未将文档检查冒充新增疗效验证。
- 新增独立原生实验：0。H00＋32支尚未完成；医学有效性未被声明。
