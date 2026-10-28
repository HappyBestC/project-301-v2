# 实现清单

| 文件 | 职责 |
|---|---|
| src/core301/agent/complete_decision.py | 严格 draft、重复 key 拒绝、输入白名单、正式 CompletePlan 构造 |
| src/core301/agent/complete_provider.py | 复用配置与 OpenAI 客户端；单次有上限请求；原始响应/usage/错误记录 |
| src/core301/agent/prompts/treatment_decision_m3a.md | 新版本独立 Prompt |
| src/core301/research_runtime/m3a_runner.py | 模式选择、预检、决策阶段、证据来源和最终状态 |
| src/core301/research_runtime/runner.py | 唯一既有源码修改：新增可选 workflow；观测后绑定模型计划，其余复用原执行闭环 |
| src/core301/research_runtime/m3a_verify.py | 只读核验真实观测、模型原文、合同、调度和原生证据关系；无重运行 |
| tests/m3a/test_decision.py | 输入、输出、HTTP Mock、资源及模拟执行集成、预检阻断 |

未修改正式 CompletePlan/Catalog/manager/coordinator、动作适配器、冻结伤情及复合配置、旧医学 Prompt、14 条评价规则。源码与配置原文件 SHA 比对见 validation/change_audit.json；before_sha.json 为本次开始时快照。

调用限制在 Provider 实例和 runner 两层落实：Provider 第二次调用直接拒绝；runner 决策只调用一次，成功后的调度/执行不重新生成计划。SDK 禁止内部自动重试。未知模型/参数/API 失败不能换固定计划。

错误日志只保留 API 异常类型和状态码，避免异常字符串携带认证头/URL；request 文件没有 key/base_url。服务响应保留原始 message、真实 model、usage；费用未提供时为 null。预检从已有配置加载，不修改配置、不扫描其他工程。

预检失败时也有 run_summary、run_manifest、空原生动作列表、资源快照、NOT_RUN 评价结果及 SHA256 索引。没有响应时不生成虚构 llm_response 或 treatment_decision。成功路径的 treatment_plan.json 是既有评价接口要求的别名，和 complete_plan.json 内容相同，不是第二个计划。
