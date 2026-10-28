# 科研模块状态

> 2026-10-19 M3-B 更新：两个隔离原生Worker、中央共享账本与同步时钟已真实验证；A合法治疗，B资源恢复后因180秒协议阻断，整体 M3B_DUAL_PATIENT_PARTIAL，真实等待推进已验证。全量回归1101通过，详见 [双患者报告](m3b_dual_patient_runtime/README.md)。

> 2026-10-19 M3-A 更新：新增真实 Treatment draft → CompletePlan → 既有执行闭环接口，离线回归 1077 passed；真实 gpt-6-sol 单次决策已进入 Pulse，状态 M3A_REAL_AGENT_EXECUTION_PASS，正式评价 NOT_EVALUABLE。详见 [本轮报告](m3a_real_treatment_agent/README.md)。下文为此前基线记录；当前单场景接入与验证范围以本轮报告为准。

状态针对下述范围；IMPLEMENTED不代表临床认证或真实端到端联调。

| 模块 | 状态 | 源码与证据 |
|---|---|---|
| 十类单伤固定模型 | IMPLEMENTED | runtime/v2/restricted_registry.py、contracts/v2；tests/v2与冻结TEN配置 |
| 五类复合固定AB | IMPLEMENTED | runtime/v2_1；tests/v2_1及admission_v2.json逐文件哈希 |
| 十二动作映射 | IMPLEMENTED | pulse/v2、runtime/v2_1/resources.py；Catalog精确十二动作、complete_dispatch覆盖 |
| 旧八动作合同/兼容 | IMPLEMENTED | contracts/treatment.py、dispatch/complete_contracts.py；678基线回归 |
| Treatment Agent V1 | IMPLEMENTED | agent/llm_provider.py、原Prompt；test_llm_provider/test_treatment_prompt/HTTP Mock |
| Treatment Agent完整计划输出 | NOT_INTEGRATED | 当前真实Provider仍为V1；只有显式桥接、ManualProvider和研究fixture |
| Resource Scheduling Agent | IMPLEMENTED | dispatch/providers.py/service.py、ETA/TaskEvent；test_dispatch*，本轮无真实LLM调用 |
| M1资源模型 | IMPLEMENTED | resource_model_m1设计、shared_resources/catalog.py、原COSTS；临床需求另列NOT_VERIFIED |
| M2-A共享账本 | IMPLEMENTED | shared_resources/manager.py；shared_resources测试、14条Demo记录 |
| M2-B共享调度 | IMPLEMENTED | shared_integration.py；shared_dispatch测试、释放重试Demo |
| M2-C完整合同 | IMPLEMENTED | complete_contracts.py、完整计划→协调器→同账本；45项原新增测试及三动作Demo |
| 当前Pulse适配 | IMPLEMENTED | pulse/session.py和v2专用路径；单元替身+原历史受限验证；本轮只初态烟雾检查 |
| 新观测冻结契约 | PARTIAL | observation_candidate_v2、冻结schemas；档案VERIFIED但PENDING/NOT_ACTIVATED |
| 十四锁定规则与原计算器 | IMPLEMENTED | 正式V2E规则文件、adapter→calibrate→offline→candidate_eval；本轮哈希/14规则AST完整性检查 |
| 十四规则主Runtime闭环 | NOT_INTEGRATED | 原core301.evaluation仍为兼容评价，不能视为完整规则闭环 |
| CompletePlan真实Pulse执行 | NOT_INTEGRATED | 现无连接到专用执行器的完整方案适配器 |
| M3双Agent反馈/重规划 | NOT_INTEGRATED | 路线记录，未开发 |
| Unity横向联调 | OUT_OF_SCOPE | 由独立project-301承担，不是科研交付验收目标 |
| 临床资源规格/资质/时长 | NOT_VERIFIED | M1 OPEN_QUESTIONS；research_fixture不等于clinical_design |

本轮测试总数为1028通过、0失败、26个integration用例deselected；其中包含原678集合，不相加。本轮最新日志位于validation/，清理和测试差异见RESEARCH_CLEANUP_REPORT.md；旧迁移报告仅作历史。

| 组织与兼容项 | 状态 | 说明 |
|---|---|---|
| V1文档清理 | IMPLEMENTED | 8份纯历史文档移除，根冻结目录消失 |
| V1必要配置隔离 | IMPLEMENTED | 两份YAML原样移入config/compatibility/v1；FROZEN_ROOT仅兼容别名 |
| 实验目录及记录规范 | IMPLEMENTED | 仅空目录与规范，不含Baseline/消融/失败归因实现 |
| V1兼容退出 | PARTIAL | 当前真实输出/Context及调度资产生命周期仍依赖旧实现，见LEGACY_DEPENDENCY_AUDIT |
