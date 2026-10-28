# 场景选择与固定范围

先核查基线、审查报告、四份参考材料、M1—M2-C以及原生/规则代码，选择依赖最少的一种基础伤情。

|候选|正式配置/原生执行|完整计划/资源|锁定规则的额外证据|选择|
|---|---|---|---|---|
|脱水→补液|TEN配置 .2/.4/.6；PatientInitializer从Condition初始化；有Saline执行|CompletePlan可表达；medic+saline袋+iv_access；需核实实际投入和袋结束|V2E-12需匹配健康H0/H1、合法Control、总体液/血量及安全Na；当前独立包绑定Soldier|未选：初始化、耗材及参考依赖更多|
|开放气胸→胸封|Left .6；固定ChestOcclusiveDressing|CompletePlan可表达；medic+封闭敷料包|V2E-07需合法Control、终点通路机制及高频证据，独立患者绑定|未选：机制采集与耗材确认更多|
|外出血→研究控源|RightLeg .4；固定StandardMale状态；原CaseRuntime/ProxyAdapter有机制确认|CompletePlan一个动作；medic×1，simulated_external_source_control权限，无stock|V2E-01需匹配Control和单源机制；无健康参考/胸腔高频特殊需求；独立适配器仍绑定Soldier|选定：最少执行与资源依赖，能够合法输出不可评价|

## 九项准入核查

1. 正式配置：`research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json` 的external_hemorrhage，profile `301.v2.phase1.research.1`。
2. 患者初态：独立Pulse目录的 `states/StandardMale@0s.json`、`patients/StandardMale.json`；`pulse/v2/session.py`逐文件校验原protocol_book SHA和Pulse版本4.3.2。
3. 初始化：`CaseRuntime.prepare` 调用既有 `InjuryAdapter.convert_dynamic`，60秒施加Hemorrhage External / RightLeg / .4，再推进120秒。
4. 计划：`CompletePlan`保留run_id、plan_id、action_instance_id、固定scope、区室及空前置依赖；单动作合法。
5. 资源：原Catalog需求为stock空、medic×1、simulated_external_source_control；已有manager实际预留，不复制库存。
6. fixture：`research_scene({'medic':1})`，同地点scene，使用其显式研究能力/权限；没有运输、小队或设施容量，也不推断临床资质。
7. 规则：V2E-01，01仅E/I不适用P；原JSON/AST及参数SHA不变。
8. 评价证据：真实同源控源与301帧已获得；合法Control和独立Soldier来源未获得，不能输出E/P/I。
9. 独立运行：run-002已在新工程和独立Pulse依赖运行完成，无原横向工程数据读取。

## 固定参数

- 患者：StandardMale固定状态，病例patient_id仅作关联，不重命名原生患者或伪装为Soldier。
- 伤情：external_hemorrhage，RightLeg，Severity=0.4，单源。
- 时间：加载0s→60s施伤→180s决策→480s终点；实际浮点时间原样保存。
- 动作：control_external_bleeding，调用原V2 TreatmentAdapter/ProxyAdapter，重提交Hemorrhage External / RightLeg Severity=0。
- 资源：research_fixture的medic令牌1，无一次性消耗，不将其称临床人数标准。
- 观察：原生公共十三字段及四诊断，每秒一帧；不是新版十五项全局激活。

没有为了E选择更轻Severity、改时间窗或新建替代代理。未生成新对照，因为现有独立评价入口首先要求不同患者来源；补一条StandardMale Control本身也不能消除这个固定绑定。本轮按用户允许的EXECUTION_PASS / EVALUATION_NOT_EVALUABLE完成最小连接，完整可评分证据另行收口。
