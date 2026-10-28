# M2-C 真实合同与能力审查

2026-10-19。根据 M1 三份模型/映射/盘点、M2-A 实现报告、M2-B 集成与局限报告及当前源码核查。下表 M2-B 指本轮实施前的已验收版本；M2-C 的新增结论单独列明。

“可表达/可接受输出”不是证明模型实际生成；“可分配”不是允许临床实施或已执行 Pulse。本轮没有调用真实 LLM 或 Pulse。

## 十二动作跨层矩阵

| 救助动作 | Treatment Agent 可输出 | 旧 Dispatch 合同可表达 | M2-A 可识别 | M2-B 可分配（实施前） | Pulse 适配情况 |
|---|---|---|---|---|---|
| control_external_bleeding | 真实LLM入口拒绝；V2手工Provider能接受 | 否 | 是，RightLeg/固定scope | 否，旧枚举阻断 | V2 ProxyAdapter：匹配授权外部源的Severity=0研究代理，不是实际止血术式 |
| fluid_resuscitation | V1输出解析器接受；真实生成未测试 | 是 | 是，saline_500ml_bag+medic | 可在合法单伤范围分配；包含控源的完整方案不支持 | 原固定Saline 500mL/100mL/min载荷；V2固定scope另校验 |
| transfusion | V1输出解析器接受；真实生成未测试 | 是 | 是，blood_500ml_bag+medic | 可在合法单伤范围分配；不支持同时包含控源的完整方案 | 原固定Blood载荷；并非现实血制品兼容资格确认 |
| control_internal_bleeding | 真实LLM入口拒绝；V2手工Provider能接受 | 否 | 是，Spleen/固定scope | 否，旧枚举阻断 | ProxyAdapter：授权内部源Severity=0，不代表已模拟腹部手术 |
| occlusive_dressing | V1输出解析器接受；真实生成未测试 | 是，side | 是，固定Left | 可在单伤范围分配；胸部复合全序列不支持 | 原ChestOcclusiveDressing，V2限Left开放气胸 |
| needle_decompression | V1输出解析器接受；真实生成未测试 | 是，side | 是，固定Left | 可在单伤范围分配；钝性复合全序列不支持 | 原NeedleDecompression，V2限Left张力性气胸 |
| control_hemothorax_bleeding | 真实LLM入口拒绝；V2手工Provider能接受 | 否 | 是，固定Left | 否，旧枚举阻断 | 旧phase1 ProxyAdapter仍拒绝；后续独立hemothorax_validation与V2.1 adapters支持固定研究源控制 |
| chest_tube | V1输出解析器接受；真实生成未测试 | 是，side | 是，但必须控源在先 | 不能分配完整合法序列：所需前序不在旧合同 | 旧phase1仍reserved；独立血胸路径及复合adapters有固定TubeThoracostomy Left/30mL/min |
| intubation | V1输出解析器接受；真实生成未测试 | 是 | 是，M2-A须与通气成对 | 成对方案可分配 | 原Tracheal载荷，V2固定范围和配对限制 |
| mechanical_ventilation | V1输出解析器接受；真实生成未测试 | 是，必须插管在先 | 是，ventilator持续占用 | 成对方案可分配 | 原固定压力控制设备设置，V2固定呼吸肌受损scope；分配不启动设备 |
| supplemental_oxygen | V1输出解析器接受；真实生成未测试 | 是 | 是，固定研究氧源/接口/medic | 单伤范围可分配；火灾复合完整序列不支持 | V2覆盖为NC .5L/min/425L；旧V1 NRB路线不能混同；本轮不改参数 |
| remove_from_exposure | 真实LLM入口及V2 TreatmentPlan均不能输出；独立暴露计划/复合bundle表达 | 否 | 是，evacuation_team与路径/环境凭据 | 否，旧枚举阻断 | exposure_session/environment_action及V2.1 adapters修改环境；不等于实际运输或到达 |

M2-C结果：十二正式动作均能由 `CompletePlan` 在各自合法研究scope表达，全部已通过至少一个完整计划的真实资源预留测试；五类复合AB序列也通过同一调度入口。仍不表示任意十二动作排列都合法。

`inhaled_albuterol`：V2通用枚举保留，但未正式开放；不在 M2-A Catalog 或 M2-C Literal 中，拒绝。不能因为 `contracts/v2/treatment.py` 的docstring写“twelve”便认定其等于本轮十二正式业务动作——该枚举包含albuterol，却不含环境移除。

## 文件级证据

| 文件/符号 | 实际结论 |
|---|---|
| src/core301/agent/interface.py、agent/llm_provider.py:LLMTreatmentProvider.create_plan | 导入contracts.treatment.TreatmentPlan；输出JSON必须经过V1校验。没有完整计划版本、action_instance_id、scope或十二动作生成入口 |
| src/core301/agent/prompts/treatment_decision.md | V1医学决策边界；本轮原字节保留 |
| src/core301/agent/v2/manual_provider.py | 接受调用者给定V2计划并返回副本；是手工fixture，不是LLM扩展能力 |
| src/core301/contracts/treatment.py | 原八动作、side、互斥及插管先于通气；不得擅改 |
| src/core301/contracts/v2/treatment.py | 额外控源、compartment、更多互斥/顺序校验；albuterol仅合同保留；无环境动作 |
| src/core301/runtime/v2_1/contracts.py:CompositePlan | pattern_id与bundle；正式资源校验采用固定AB，不能自动认为A/B/BA也准入 |
| src/core301/dispatch/models.py | DispatchInput.treatment_plan绑定V1；Facility/MedicalTeam能力也受旧八动作限制，并非仅替换plan字段即可 |
| src/core301/dispatch/shared_integration.py（M2-B） | 原ACTION_CONTRACT_UNSUPPORTED整组拒绝，M2-C仅在新版CompleteDispatchInput下启用完整动作验证 |
| src/core301/dispatch/shared_resources/catalog.py | 直接复用runtime/v2_1/resources.COSTS和冻结十类/五类范围；validate_scope调用已有V2治疗规则，补血胸前序和精确AB |
| src/core301/pulse/treatment_adapter.py、pulse/v2/treatment_adapter.py、pulse/v2/proxy_adapter.py | 原固定参数及phase1受限适配；不读M2-C合同，不由本轮生成新native参数 |
| src/core301/runtime/v2/hemothorax_validation.py、pulse/v2/hemothorax_session.py | 后续独立血胸固定研究路径，不能只根据旧phase1 RESERVED否定其存在 |
| src/core301/runtime/v2/exposure_validation.py、pulse/v2/exposure_session.py | 独立暴露环境计划和环境条件载荷；不是物理运输事件 |
| src/core301/runtime/v2_1/adapters.py、runtime.py | 固定AB动作到原生/代理/环境载荷，依赖和会话约束；M2-C没有调用execute |

冻结依据：`research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json`；`config/v2_1_battle_composite_patterns.yaml`（registry自带SHA检查）；M1 `CURRENT_ACTION_INVENTORY.md`、`ACTION_RESOURCE_MAPPING.md`、`RESOURCE_MODEL_V1_DESIGN.md`。旧/后续证据版本不混用。

## 各层验收

| 层次 | 状态 | 证据及精确含义 |
|---|---|---|
| 合同表达 | PASS | 十二Literal动作、稳定实例ID/目标/顺序/依赖/版本/研究范围；JSON往返 |
| 组合校验 | PASS | 复用Catalog/V2与精确AB；错序、错侧、额外参数、互斥、未知组合拒绝 |
| 资源映射 | PASS | 直接转换原M2-A Plan；stock/holds/权限从原Catalog解析，不新建成本表 |
| 调度集成 | PASS | 原service/Fixed Provider及原LLM Provider的HTTP Mock均收到完整计划，原五字段proposal不变 |
| 原子分配 | PASS | 真正M2-A reserve；全组失败及线程竞争；旧、新输入同run竞争一个账本 |
| 旧合同兼容 | PASS | 冻结文件原字节保留，633项原回归通过 |
| 复合伤覆盖 | PASS（合同/研究资源层） | 五种AB各自通过合同、解析、Agent传递和预留；各自资源不足整组失败 |
| 救助Agent接入 | PARTIAL | 非侵入旧计划桥接可用；真实LLMTreatmentProvider仍为V1，不能端到端生成十二动作，未测试其真实输出 |
| Pulse执行 | BLOCKED（本轮未接入/未运行） | 无CompletePlan→执行宿主桥接；已有适配器存在不等于本轮执行验证；本轮禁止运行真实仿真 |
