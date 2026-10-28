# V1及历史依赖审查

2026-10-19。区分文档、数据合同与Python实现；不以文件名V1/V2判断去留。完整逐文件分类见research_baseline/cleanup/FILE_CLASSIFICATION.json，实际import与准入哈希边见DEPENDENCY_GRAPH.json。

## 根目录旧冻结目录逐项结论

| 文件 | 运行/配置/测试引用 | 本轮处理与后果 |
|---|---|---|
| 冻结契约总览.md | 无Python读取、无当前正式V2配置加载；仅历史说明 | 删除；以RESEARCH_SCOPE/基线替代，无运行影响 |
| 冻结/6类典型战伤模式_冻结版.md | 同上；六模式测试读取的是YAML而非此文档 | 删除；正式范围仅五复合，旧六模式不提升为科研模型 |
| 冻结/10类基础伤情模板_冻结版.md | 无运行/必要测试读取 | 删除；正式受限十类配置及基线替代 |
| 冻结/最小伤员数据模型_v1_冻结版.md | 无运行读取；Python合同独立存在 | 删除文档，保留实际合同 |
| 冻结/AgentCaseContext_v1_冻结版.md | 无运行读取 | 删除文档，保留Agent上下文代码 |
| 冻结/PatientObservation_v1_冻结版.md | 无运行读取 | 删除文档，保留当前观测代码 |
| 冻结/TreatmentPlan_v1_冻结版.md | 无运行读取；Provider使用Python schema | 删除文档，保留八动作合同和真实Prompt |
| 冻结/Frozen_v1_契约一致性检查.md | 历史人工检查说明，无必要测试读取 | 删除；当前测试和哈希报告替代 |
| 配置/injury_templates.yaml | contracts/casualty.py导入时加载；Context/真实Treatment Provider间接依赖 | 原样迁至config/compatibility/v1/配置；不可替换为V2配置而改变旧输出语义 |
| 配置/battle_injury_patterns.yaml | tests/test_contracts.py::test_six_patterns、evaluation/demo.py::demo_inputs；无正式V2配置引用 | 原样迁至兼容目录；仅旧六模式兼容覆盖，不新增科研范围 |

上述八份Markdown均只服务历史开发说明，删除不影响科研运行。原件在原横向项目及独立恢复档案，主工程不再保留副本。FROZEN_ROOT名称作为API兼容别名保留，指向LEGACY_COMPATIBILITY_ROOT；无软链接回旧冻结目录。

## 暂时保留的兼容实现及退出条件

| 文件/模块 | 实际使用者与保留原因 | 移除条件 / 与M3-A关系 |
|---|---|---|
| contracts/casualty.py | 动态旧CasualtyInput/KnownInjury；context/known_injury_projector、旧Pulse InjuryAdapter使用 | 新Context与所有旧病例读取方迁移后；与M3-A相关，不能仅换输出schema就删 |
| contracts/context.py、context/builder.py、context/known_injury_projector.py及包入口 | agent/interface、llm_provider、runtime/case_runtime构建V1 AgentCaseContext | M3-A明确新版输入契约并迁移调用方后 |
| contracts/treatment.py及包导出 | 真实LLM八动作输出、dispatch模型和完整计划显式桥接、旧执行器 | 新版Provider与兼容边界另行版本化并验证后；M3-A主要债务 |
| contracts/observation.py | 当前Pulse projector、V1 Context与旧评价结果 | 新观测激活及上下游迁移后，不只取决于M3-A |
| agent/interface.py、llm_provider.py、manual_provider.py、agent/prompts/treatment_decision.md | 真实现有救助链路；Prompt未修改 | M3-A建立版本化完整输出后再审查旧分支 |
| agent/llm_config.py | 两个Agent共同读取当前配置，虽起源旧工程仍为研究共享基础 | 无删除理由；不是纯历史负担 |
| runtime/case_runtime.py、runtime/capability.py、cli.py | 真实Treatment LLM入口、能力约束、单病例执行；大量当前回归 | 研究新入口覆盖并取代旧研究运行链路后；不能直接清空 |
| pulse/injury_adapter.py、pulse/treatment_adapter.py | 旧Runtime及V2适配复用scalar/原动作映射 | 所有复用者迁移后；含共享原语，不建议仅因V1来源重写 |
| dispatch/models.py、manager.py、events.py、validation.py、eta.py、eta_validation.py、clock.py | SharedDispatchCoordinator沿用队伍/车/设施、TaskEvent、ETA和任务生命周期 | 仍为M2核心依赖；不是只服务Unity，不在M3-A自动删除 |
| evaluation/*.py、config/treatment_evaluation.yaml、tests/fixtures/treatment_evaluation.yaml | 原反事实/终止评价器及测试，保持旧执行接口和可复现对照；不等于V2E十四规则在线闭环 | 版本化研究评价入口替代并保留必要算法对照后；不以删除测试代替迁移 |
| fixtures/casualties_v1.json、first_case.json、first_plan.json、resource_state.py | CLI、真实Provider离线测试、Context构建/既有研究fixtures | 新版独立场景覆盖所有用途后；未当正式V2全范围fixture |
| config/compatibility/v1/配置/*.yaml | 见上表两条实际读取链 | 对应旧合同/六模式测试和Demo不再使用时分别移除 |

contracts/base.py等严格类型基础、共享Pulse session/projector、Provider配置和M2-A/B/C主体为科研核心，不因服务V1调用方而降为可删历史代码。每个源文件的保留分类及引用边可由机器清单复核。

## 已清理的周边与保留证据

未被当前CLI/测试/源码引用的casualties_v2.json、casualties_v3.json历史横向批次已移除；历史snapshot来源索引可能仍提到其来源名，这些是过去副本的来源记录，不是当前运行准入对两个文件的哈希依赖。

M2-A旧DELIVERY_SHA256.json是过往交付索引，非运行输入，已归档移除；M2-A源码/测试/实现报告均保留。横向全树压缩目录记录和迁移中间失败日志也移出主工程，迁移最终通过结果保留于history/migration。

大量research_artifacts确实不能删：复合准入588项proof、单伤准入8项evidence、受限风险和现有fixture、冻结manifest来源、原AST与参考算法。相应文件原样保留；没有为缩小目录绕过SHA，也不将旧R01—R14重新引入。现未发现可安全删除、仅服务Unity的Python模块；保留的旧队/车/容量实现有明确科研调度依赖。
