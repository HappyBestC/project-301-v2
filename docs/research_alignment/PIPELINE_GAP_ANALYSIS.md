# 完整科研数据流缺口

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

**整体 PARTIAL：存在可运行的分段工程实现，没有证据证明所列完整链路已经连通。** 本表“Mock已验证”只指既有测试/档案；“真实Pulse”仅指既有受限研究记录，本轮没有新运行；“真实LLM未验证”不否认更早可能用过旧模型，而是当前目标版本没有足够证据。

|连接|代码实现/真正接通|Mock或离线证据|真实LLM证据|真实Pulse证据|当前缺口/状态|
|---|---|---|---|---|---|
|V2伤情配置→Pulse初始化|有：v2 research_router、injury_adapter、v2_1 native_backend；受限固定入口接通|tests/v2、tests/v2_1含门控/替身；既有验收|不涉及|十类/五类固定工程验收历史记录；本轮未重跑|统一请求合同与患者扩展不成立；固定范围MATCHED|
|Pulse→PatientObservation|旧projector接通；新版15项catalog/projector存在但未全量运行接入|新版档案205/207，2个N1保留|新版未验证|旧公共字段及诊断有历史采集；非全病例15项|新增COHb/Na实时公开投影、授权结果事件缺失；PARTIAL|
|PatientObservation→Treatment Agent|旧AgentCaseContext和LLMTreatmentProvider接通；新版合同未接|旧provider合同/HTTP Mock；新版有模型校验|新版15项真实上下文未验证|原生观察路径存在，不等于送入真实LLM|上下文版本/可见性消费桥接；PARTIAL|
|Treatment Agent→完整12动作TreatmentPlan|Provider仍输出旧八动作；CompletePlan有独立实现及fixture/旧计划显式桥接|tests/complete_dispatch有往返、非法动作/依赖测试|12动作新版生成未验证|不涉及生成；native固定计划不等于Agent生成|稳定ID/scope宿主管理、新版输出解析与Prompt另阶段；PARTIAL|
|完整TreatmentPlan→Resource Scheduling Agent|service decode_dispatch_input识别完整版本，provider传递完整计划|Fixed及HTTP Mock已有完整载荷验证|真实模型新版调度未验证|未涉及|入口已接合同，真实LLM能力尚无证据；PARTIAL|
|调度Agent→M2-A/B/C共享校验/预留|有：shared_integration/coordinator和同一manager；后端重验快照/能力/地点/身份|真实内存manager竞争、原子失败、幂等、17场景记录|当前证据为Fixed/Mock|未涉及|研究资源层MATCHED；临床未知/跨进程持久化未实现|
|资源预留→实际执行动作|共享manager有begin/consumption/execution/release接口；旧V2 Runtime有另一套局部资源fixture|宿主模拟回执/未知隔离测试|全链路未验证|旧固定执行有原生记录；M2-C计划执行未验证|CompletePlan→正确受限executor及回执→账本桥接缺失；PARTIAL|
|实际动作→Pulse生理更新|原生submit/advance/read及guard均有；固定AB按.02s顺序推进|session替身和运行门控测试|不等于真实Agent选择的动作有效|既有十类/五类及单规则实验支持固定范围更新|不能以accepted代替剂量完成/机制生效；新版共享链路UNVERIFIED，既有固定层MATCHED|
|Pulse更新→EvaluationObservation|candidate replay/models支持历史时序、诊断、事件、动作；非当前完整实时导出|历史B1/N1及结构验证|不涉及|历史采集可回放；新Runtime实时新版输出未验证|在线采样、事件/动作身份、授权、顺序和配对来源整合；PARTIAL|
|EvaluationObservation→V2E-01—14|原AST和manifest适配器有入口；新版容器不能直接喂入适配器|旧规则382项记录、研究适配器校验；非本轮新测试|不涉及|历史报告14条首轮AST输出；本地大型原始数据缺失|映射至证据manifest、匹配control/healthy、患者及scope门控缺失；PARTIAL|
|评价结果→后续Agent决策|未见统一Runtime回调/重规划；当前首轮/固定episode拒重复治疗|无目标完整反馈测试|未验证|未验证|需明确可见结果、下一决策时点、设备占用及禁止重放语义；UNVERIFIED|

## 可追踪调用边界

- 初始化/执行：[src/core301/runtime/v2/research_router.py](../../src/core301/runtime/v2/research_router.py)、[src/core301/runtime/v2/case_runtime.py](../../src/core301/runtime/v2/case_runtime.py)、[src/core301/runtime/v2_1/runtime.py](../../src/core301/runtime/v2_1/runtime.py)、[src/core301/runtime/v2_1/native_backend.py](../../src/core301/runtime/v2_1/native_backend.py)。
- 观察/Agent：[src/core301/pulse/observation_projector.py](../../src/core301/pulse/observation_projector.py) → [src/core301/context/builder.py](../../src/core301/context/builder.py) / [src/core301/contracts/context.py](../../src/core301/contracts/context.py) → [src/core301/agent/llm_provider.py](../../src/core301/agent/llm_provider.py)。新版模块在 `observation_candidate_v2/`，没有替换这条运行调用链。
- 完整调度：[src/core301/dispatch/complete_contracts.py](../../src/core301/dispatch/complete_contracts.py) → [src/core301/dispatch/service.py](../../src/core301/dispatch/service.py) / [src/core301/dispatch/providers.py](../../src/core301/dispatch/providers.py) → [src/core301/dispatch/shared_integration.py](../../src/core301/dispatch/shared_integration.py) → [src/core301/dispatch/shared_resources/manager.py](../../src/core301/dispatch/shared_resources/manager.py)。当前止于调度和可信宿主推动的生命周期，不直接提交Pulse。
- 研究评价：[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/adapter.py](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/adapter.py) → [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/calibrate.py](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/calibrate.py) → 锁定definitions。该链读取额外文件/事实，不是对单个patient_observation打分；不能只拿15指标均值绕过对照、时窗和机制。

## 验证层次不能互相替代

|证据|能支持什么|不能支持什么|
|---|---|---|
|十类/五类ACCEPTANCE与固定协议|历史受限原生工程能力及已登记范围|任意档位/患者、真实Agent规划、新版共享调度闭环|
|M2-C 678项、17场景、5/5复合预留|完整合同与研究共享资源机制；HTTP载荷正确|真实模型决策质量、完整计划Pulse执行|
|Observation归档205/207|契约/投影/历史回放工程准备；N1例外明确|新版Runtime已激活、所有Agent收到全部十五项|
|规则SHA与原AST|锁定内容完整、当前可追踪运算入口|当前生产评分启用、缺数据也可打分|
|历史十四条AST研究结果|已有报告记录首轮10E/3P/1I及异常|全部分支/复合效果通过、原始数据在新工程已完整复算|
|迁移t=0原生smoke|新环境基本加载与初始读数能力|任何治疗效果、时间推进或LLM链路验证|

报告里的路径缺失和历史绝对路径只作为证据可用性问题记录。本轮没有沿它们读取原横向项目，也没有重新运行旧驱动以“补齐验证”。完整科研链路缺口不应通过修改冻结规则或扩大fixture权限来消除。
