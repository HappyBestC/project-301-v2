# 基础伤情与复合伤对照

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

## 十类基础伤情

材料：[docs/research_references/十类伤情和救助动作.md](../../docs/research_references/十类伤情和救助动作.md)。正式表：[research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json](../../research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json)。

下表最后一列依次表示“材料与正式固定范围一致性 / 当前统一 Agent 全链路”。动作列是允许集合，**不是所有列出动作都同时执行**：出血须先控源，补液与输血是互斥支持分支；气道须插管后通气；血胸须控源后置管。

|injury_type|材料/模型可表达部位|正式准入部位、Severity 或环境|Pulse 初始化机制|正式动作集合|决策→终点(s)|状态|
|---|---|---|---|---|---|---|
|`external_hemorrhage`|LeftArm / RightArm / LeftLeg / RightLeg|{'compartment': 'RightLeg'}；[0.4]|Hemorrhage / External；动态 Severity|`control_external_bleeding` →/或 `fluid_resuscitation` →/或 `transfusion`|180→480|MATCHED / PARTIAL|
|`abdominal_internal_hemorrhage`|LeftKidney / RightKidney / Liver / Spleen / Splanchnic / SmallIntestine / LargeIntestine|{'compartment': 'Spleen'}；[0.4]|Hemorrhage / Internal；动态 Severity|`control_internal_bleeding` →/或 `fluid_resuscitation` →/或 `transfusion`|180→480|MATCHED / PARTIAL|
|`open_pneumothorax`|Left / Right，单项不接受 Both|{'side': 'Left'}；[0.6]|TensionPneumothorax / Open；动态 Severity|`occlusive_dressing`|180→480|MATCHED / PARTIAL|
|`closed_tension_pneumothorax`|Left / Right，单项不接受 Both|{'side': 'Left'}；[0.6]|TensionPneumothorax / Closed；动态 Severity|`needle_decompression`|180→480|MATCHED / PARTIAL|
|`respiratory_muscle_impairment`|无部位/侧别|{}；[0.4]|RespiratoryFatigue；动态 Severity|`intubation` →/或 `mechanical_ventilation`|180→480|MATCHED / PARTIAL|
|`impaired_alveolar_exchange`|无部位/侧别|{}；[0.2, 0.4, 0.6]|ImpairedAlveolarExchangeExacerbation；动态 Severity|`supplemental_oxygen`|180→480|MATCHED / PARTIAL|
|`dehydration`|无部位/侧别，Condition|{}；[0.2, 0.4, 0.6]|Dehydration Condition；患者初始化，不能作为运行中动态 Action|`fluid_resuscitation`|180→480|MATCHED / PARTIAL|
|`hemothorax`|Left / Right，单项不接受 Both|{'side': 'Left'}；[0.8]|Hemothorax；动态 Severity|`control_hemothorax_bleeding` →/或 `chest_tube`|660→960|MATCHED / PARTIAL|
|`carbon_monoxide_exposure`|气体参数，无 Severity|CO=0.005；O₂=0.21|ChangeEnvironmentalConditions：CO/O₂/余量气体；不是 Severity|`remove_from_exposure`|960→1860|MATCHED / PARTIAL|
|`environmental_hypoxia`|气体参数，无 Severity|CO=0；O₂=0.12|ChangeEnvironmentalConditions：CO/O₂/余量气体；不是 Severity|`remove_from_exposure`|360→660|MATCHED / PARTIAL|

八类带 Severity 的材料候选档位为 0.2/0.4/0.6/0.8/1.0，不能推导其所有部位和患者组合均获准。`contracts/v2/injury.py:SEVERITIES` 还允许 0；正式 `protocol_book.validate_injury_scope` 拒绝不在固定档位/部位的病例，0 只在停源代理中有研究操作意义，不是已验收的新伤情档位。左右分别建模也不自动批准双侧伤。

**患者范围：**受限 Runtime 绑定 StandardMale 固定状态/初始化。`pulse/v2/protocol_book.py` 固定患者与状态 SHA；脱水从 StandardMale 加 Condition 初始化。`patient_id` 是病例身份，不授权任意性别、年龄、体型。后续十四规则的独立 Soldier 男性实验属于另一套 pinned patient / manifest 证据，不能反向扩大 Runtime 患者准入。正式 10/10 工程接受见 [research_artifacts/v2_restricted_engineering_baseline_v1.0/ACCEPTANCE.json](../../research_artifacts/v2_restricted_engineering_baseline_v1.0/ACCEPTANCE.json)；本轮没有重新做十类原生实验。

### 实现入口和模型范围差异

- [src/core301/contracts/v2/injury.py](../../src/core301/contracts/v2/injury.py) 的旧 `INJURY_TYPES` 有十项，但含 bronchoconstriction、acute_lung_impairment_ards，且不含两个环境 injury_type。它是历史候选数据模型，**不是正式十类清单**。[src/core301/runtime/v2/restricted_registry.py](../../src/core301/runtime/v2/restricted_registry.py) 的正式 REGISTRY 才与本次材料的十类一致；环境走专用暴露合同。统一请求合同仍 PARTIAL。
- [src/core301/runtime/v2/research_router.py](../../src/core301/runtime/v2/research_router.py): `open_research_case` 分发 phase1、血胸及两种环境路径；[src/core301/pulse/v2/injury_adapter.py](../../src/core301/pulse/v2/injury_adapter.py) 明确脱水初始化边界；[src/core301/pulse/v2/exposure_session.py](../../src/core301/pulse/v2/exposure_session.py) 构造气体环境。
- [src/core301/pulse/v2/protocol_book.py](../../src/core301/pulse/v2/protocol_book.py) 的 phase1 血胸 BLOCKED/RESERVED 与后续 restricted 血胸准入并存。属于分阶段入口边界，不是所有血胸均禁用，也不是旧适配器已自动升级。
- [src/core301/runtime/v2/restricted_admission.py](../../src/core301/runtime/v2/restricted_admission.py) 与 [tests/v2/test_restricted_admission.py](../../tests/v2/test_restricted_admission.py) 核对受限证据；[tests/v2/test_restricted_router.py](../../tests/v2/test_restricted_router.py) 是路由/门控测试，不替代全部真实 Pulse 运行。

“文档定义支持但 Runtime 未验证”：RightLeg 0.4 之外的外出血部位/档位、Spleen 0.4 之外的内出血组合、右侧气胸/血胸、其他患者及任意复合均不能从模型可表示推为已验证。肺泡/脱水的 0.2/0.4/0.6 是受限工程档位，但后续规则首轮 Soldier 结果主要为 0.4；应分别看工程准入和独立规则实验覆盖。

## 五类复合伤精确对照

材料：[docs/research_references/五类组合伤.md](../../docs/research_references/五类组合伤.md)；实际读取 [config/v2_1_battle_composite_patterns.yaml](../../config/v2_1_battle_composite_patterns.yaml)（内容为 JSON 兼容 YAML），并对照 [research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIVE_COMPOSITE_CONFIGURATIONS.json](../../research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIVE_COMPOSITE_CONFIGURATIONS.json)、`FIXED_PROTOCOLS.json`。

|pattern_id|固定组成|环境参数|精确 AB 序列|决策→终点(s)|
|---|---|---|---|---|
|`penetrating_thoracic_composite_v2`|open_pneumothorax Left 0.6 + hemothorax Left 0.8|普通空气；无附加暴露|occlusive_dressing → control_hemothorax_bleeding → chest_tube|660→960|
|`blunt_thoracoabdominal_composite_v2`|abdominal_internal_hemorrhage Spleen 0.4 + closed_tension_pneumothorax Left 0.6|普通空气；无附加暴露|control_internal_bleeding → fluid_resuscitation → needle_decompression|180→480|
|`blast_hemorrhage_respiratory_composite_v2`|external_hemorrhage RightLeg 0.4 + respiratory_muscle_impairment  0.4|普通空气；无附加暴露|control_external_bleeding → fluid_resuscitation → intubation → mechanical_ventilation|180→480|
|`fire_co_alveolar_composite_v2`|carbon_monoxide_exposure + impaired_alveolar_exchange  0.4|{'co': 0.005, 'oxygen': 0.21}|remove_from_exposure → supplemental_oxygen|960→1860|
|`trapped_hypoxia_dehydration_composite_v2`|environmental_hypoxia + dehydration  0.4|{'co': 0, 'oxygen': 0.12}|remove_from_exposure → fluid_resuscitation|360→660|

胸部穿透组合血胸 60s 起病、开放气胸 540s 起病、660s 决策；其余动态伤/暴露通常 60s 起病，脱水在初始化时加载。组合时间线不是两种单伤时间线简单叠加。每个 native 动作之间推进 0.02s。无新增 Severity，不能从底层任意注入。

|pattern_id|配置层|合同层|资源调度层|Pulse 执行层|
|---|---|---|---|---|
|`penetrating_thoracic_composite_v2`|MATCHED：上述固定配置|MATCHED：CompositePlan；CompletePlan 校验精确 AB|MATCHED：M2-C fixture 整组预留；完整执行桥接 PARTIAL|MATCHED：既有固定 AB 受限适配/验收；M2-C 新计划原生闭环 UNVERIFIED|
|`blunt_thoracoabdominal_composite_v2`|MATCHED：上述固定配置|MATCHED：CompositePlan；CompletePlan 校验精确 AB|MATCHED：M2-C fixture 整组预留；完整执行桥接 PARTIAL|MATCHED：既有固定 AB 受限适配/验收；M2-C 新计划原生闭环 UNVERIFIED|
|`blast_hemorrhage_respiratory_composite_v2`|MATCHED：上述固定配置|MATCHED：CompositePlan；CompletePlan 校验精确 AB|MATCHED：M2-C fixture 整组预留；完整执行桥接 PARTIAL|MATCHED：既有固定 AB 受限适配/验收；M2-C 新计划原生闭环 UNVERIFIED|
|`fire_co_alveolar_composite_v2`|MATCHED：上述固定配置|MATCHED：CompositePlan；CompletePlan 校验精确 AB|MATCHED：M2-C fixture 整组预留；完整执行桥接 PARTIAL|MATCHED：既有固定 AB 受限适配/验收；M2-C 新计划原生闭环 UNVERIFIED|
|`trapped_hypoxia_dehydration_composite_v2`|MATCHED：上述固定配置|MATCHED：CompositePlan；CompletePlan 校验精确 AB|MATCHED：M2-C fixture 整组预留；完整执行桥接 PARTIAL|MATCHED：既有固定 AB 受限适配/验收；M2-C 新计划原生闭环 UNVERIFIED|

[src/core301/runtime/v2_1/runtime.py](../../src/core301/runtime/v2_1/runtime.py): `execute` 非 validation 模式只准 AB，检查 case 身份、固定时刻、context、新旧请求幂等、依赖、实际原生回执及每步 guard；`acceptance` 调用组合工程风险门控，**不等同 V2E-01—14 联合疗效判定**。[src/core301/runtime/v2_1/adapters.py](../../src/core301/runtime/v2_1/adapters.py): `kinds_for` 按 A 后 B 展开，`action_payload` 转固定 Pulse 动作；[src/core301/runtime/v2_1/native_backend.py](../../src/core301/runtime/v2_1/native_backend.py) 负责初始化/采集/推进。

[research_artifacts/v2_1_restricted_engineering_baseline_v1.0/ACCEPTANCE.json](../../research_artifacts/v2_1_restricted_engineering_baseline_v1.0/ACCEPTANCE.json) 记录 5/5 受限 Runtime 准入、45 完整分支及历史 944 项测试，明确排除真实 LLM 规划和生产运行。此为既有工程验收，不是本轮实测。[research_artifacts/resource_model_m2c/TEST_REPORT.md](../../research_artifacts/resource_model_m2c/TEST_REPORT.md) 的另外 5/5 是合同、传递和研究资源预留，明确未执行 Pulse；两组证据不可合并为新版全链路验证。

`CompletePlan` 依赖为严格前序 action_instance_id；旧 CompositePlan 则由 pattern/bundle 生成原生序列。二者存在可桥接的固定业务语义，但当前没有将前者和共享账本生命周期接入后者的适配器。跨病例共享资源也不是 CompositeCase 的局部 HostResources 自动提供。

## 本轮准入与配置只读复核

正式十类表与REGISTRY集合完全一致；复合配置五项与冻结副本内容完全一致，source_sha256匹配。实际调用后续三类专用 `restricted_admission.verify_admission`（血胸/CO/低氧）3/3通过；五类 `v2_1.admission.verify_admission` 5/5通过，均只读证据哈希。phase1七类直接走CaseRuntime，不属于后续三类manifest；没有把该专用函数对phase1的拒绝算为准入失败。以上不创建引擎，不证明新的治疗运行通过。
