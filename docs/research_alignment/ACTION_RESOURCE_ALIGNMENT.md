# 十二动作与 M1—M2-C 资源一致性

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

## 全映射

M1 材料已实际读取：[research_artifacts/resource_model_m1/ACTION_RESOURCE_MAPPING.md](../../research_artifacts/resource_model_m1/ACTION_RESOURCE_MAPPING.md)、[research_artifacts/resource_model_m1/CURRENT_ACTION_INVENTORY.md](../../research_artifacts/resource_model_m1/CURRENT_ACTION_INVENTORY.md)、[research_artifacts/resource_model_m1/RESOURCE_MODEL_V1_DESIGN.md](../../research_artifacts/resource_model_m1/RESOURCE_MODEL_V1_DESIGN.md) 与 [research_artifacts/resource_model_m1/OPEN_QUESTIONS.md](../../research_artifacts/resource_model_m1/OPEN_QUESTIONS.md)。下表资源值来自实际 COSTS，不是从医学常识补入。能力 ID 是 M1 的 **PROPOSED** 医疗能力，运行时 capabilities 使用 action_type 研究令牌，两者不能视作执业资格认证。

组合编号按 [伤情报告](INJURY_ALIGNMENT.md) 表格顺序 1—5。状态依次为“研究动作/资源定义一致 / 当前完整执行链”。

|action_id|injury_type / 组合编号|Pulse 机制|M1 能力（拟议）|stock 研究耗材|holds 人员/设备|研究权限|状态|
|---|---|---|---|---|---|---|---|
|`control_external_bleeding`|external_hemorrhage；组合3|Hemorrhage External / RightLeg Severity=0|`external_source_control`|无研究扣减项|{'medic': 1}|simulated_external_source_control|MATCHED / PARTIAL|
|`control_internal_bleeding`|abdominal_internal_hemorrhage；组合2|Hemorrhage Internal / Spleen Severity=0|`internal_source_control`|无研究扣减项|{'medic': 1}|simulated_internal_source_control|MATCHED / PARTIAL|
|`control_hemothorax_bleeding`|hemothorax；组合1|Hemothorax Left Severity=0|`hemothorax_source_control`|无研究扣减项|{'medic': 1}|simulated_hemothorax_source_control|MATCHED / PARTIAL|
|`occlusive_dressing`|open_pneumothorax；组合1|ChestOcclusiveDressing Left On|`chest_wound_sealing`|{'occlusive_dressing_kit': 1}|{'medic': 1}|无额外 permission；仍需能力|MATCHED / PARTIAL|
|`needle_decompression`|closed_tension_pneumothorax；组合2|NeedleDecompression Left On|`pleural_decompression`|{'needle_kit': 1}|{'medic': 1}|无额外 permission；仍需能力|MATCHED / PARTIAL|
|`chest_tube`|hemothorax；组合1|TubeThoracostomy Left 30 mL/min|`pleural_drainage`|{'chest_tube_kit': 1}|{'medic': 1}|research_chest_tube|MATCHED / PARTIAL|
|`fluid_resuscitation`|external_hemorrhage, abdominal_internal_hemorrhage, dehydration；组合2, 3, 5|SubstanceCompoundInfusion Saline 500 mL / 100 mL/min|`iv_fluid_support`|{'saline_500ml_bag': 1}|{'medic': 1}|iv_access|MATCHED / PARTIAL|
|`transfusion`|external_hemorrhage, abdominal_internal_hemorrhage；组合无固定组合|SubstanceCompoundInfusion Blood 500 mL / 100 mL/min|`blood_support`|{'blood_500ml_bag': 1}|{'medic': 1}|iv_access|MATCHED / PARTIAL|
|`intubation`|respiratory_muscle_impairment；组合3|Intubation Tracheal|`tracheal_airway`|{'airway_kit': 1}|{'medic': 1}|无额外 permission；仍需能力|MATCHED / PARTIAL|
|`mechanical_ventilation`|respiratory_muscle_impairment；组合3|MechanicalVentilatorPressureControl；AC，FiO₂ .21，吸气压力13/PEEP5 cmH₂O，RR12，吸气1s，Slope .1s|`ventilatory_support`|无研究扣减项|{'ventilator': 1}|无额外 permission；仍需能力|MATCHED / PARTIAL|
|`supplemental_oxygen`|impaired_alveolar_exchange；组合4|SupplementalOxygen NasalCannula .5 L/min，425 L|`oxygen_delivery`|无研究扣减项|{'medic': 1, 'nasal_cannula': 1, 'oxygen_425l_source': 1}|无额外 permission；仍需能力|MATCHED / PARTIAL|
|`remove_from_exposure`|carbon_monoxide_exposure, environmental_hypoxia；组合4, 5|ChangeEnvironmentalConditions：CO=0、O₂=.21|`exposure_removal`|无研究扣减项|{'evacuation_team': 1}|research_environment_removal|MATCHED / PARTIAL|

十二个正式 action_id 全部出现在 `dispatch/complete_contracts.py:ACTION_TYPES` 与合并 COSTS；没有将 `inhaled_albuterol` 作为第十三个开放动作。组合动作通过固定 AB 覆盖其中十一项，输血在单伤另两条分支覆盖；不能因五组合未使用输血而漏掉其研究资源需求。

## 动作的真实含义与重复定义

- 三个 control_* 是重提交同源 Severity=0 的**研究控源代理**，不是止血带、外科手术或介入步骤实现。空 stock 只是研究计账无扣减项，不能称临床零耗材。
- remove_from_exposure 修改引擎环境气体；宿主须提供 protected_route_available、receiving_environment_verified。它不生成实际搬运、救护车出发/到达或转院事实。
- 正式氧疗是 V2 鼻导管 .5 L/min；旧 `pulse/treatment_adapter.py` 同名动作是 NRB 15 L/min。V2 `pulse/v2/treatment_adapter.py` 与 `runtime/v2_1/adapters.py` 明确覆盖该分支。**入口选错会改变协议**，新版桥接不得直接把所有动作交给旧 V1 适配器。当前正式 V2 路径未发现氧疗参数冲突；此为历史重复定义的集成风险。
- phase1 COSTS、血胸 COSTS 和 composite 合并表分层存在；M2 `shared_resources/catalog.py` 导入 composite 合并表，未维护另一份十二动作数字。M1 文档再次陈述同一 fixture，并不形成运行中第二套库存。

Pulse 依据：[src/core301/pulse/v2/proxy_adapter.py](../../src/core301/pulse/v2/proxy_adapter.py)、[src/core301/pulse/v2/treatment_adapter.py](../../src/core301/pulse/v2/treatment_adapter.py)、[src/core301/pulse/treatment_adapter.py](../../src/core301/pulse/treatment_adapter.py)、[src/core301/runtime/v2_1/adapters.py](../../src/core301/runtime/v2_1/adapters.py)。资源依据：[src/core301/runtime/v2/resources.py](../../src/core301/runtime/v2/resources.py)、[src/core301/runtime/v2/hemothorax_resources.py](../../src/core301/runtime/v2/hemothorax_resources.py)、[src/core301/runtime/v2_1/resources.py](../../src/core301/runtime/v2_1/resources.py)。

## 人员、设备、耗材与地点的已知/未知边界

|维度|已实现或已确认的研究事实|待确认内容及当前处理|状态|
|---|---|---|---|
|人员|medic/evacuation_team 令牌及共享实体占用|十二动作真实资质、人数、持续监护、术式团队；Q01—Q03|PARTIAL|
|设备|ventilator、nasal_cannula、oxygen_425l_source 作为 holds|电源/气源/回路、型号、途中运行、鼻导管真实复用政策；Q04—Q06|PARTIAL|
|耗材|包/袋按研究数量；Saline 与 Blood 为不同动作|真实包内组成、血型兼容、制品、温控、有效期；Q04/Q07|PARTIAL|
|地点|明确 location_id、能力/权限；环境动作路线及接收环境条件|各术式必需设施、操作位、临床可用性；Q08；未知不能当满足|PARTIAL|
|数量与时长|研究实例显式有限库存、同一仿真时钟|临床数量/准备/操作/监护/清理时长均未确认；不得由 .02s 或300s评价窗推定|UNVERIFIED|
|连续消耗|当前按氧源令牌占用、输注袋分配；执行器驱动实际剂量|尚非连续气量库存/临床计费模型；425L 和500mL不是实际全量交付证明|PARTIAL|
|临床替代方案|无已确认现实 OR 替代组合|不能将补液/输血、氧疗/通气、胸管/控源互换|UNVERIFIED|

M1 的临床知识仍是 PROPOSED / PENDING_EXPERT_REVIEW / UNKNOWN，不因 M2 工程完成变为 CONFIRMED。`manager._conditions` 对 `scope_kind=clinical_design` 返回 QUALIFICATION_UNVERIFIED，对应 INDETERMINATE，不会凭研究库存足够放行。这里没有自行提出临床标准或外部指南结论。

## M2-A/B/C 一致性与资源语义

[src/core301/dispatch/shared_resources/manager.py](../../src/core301/dispatch/shared_resources/manager.py) 提供共享状态、版本、原子整组 reserve、begin_usage、record_consumption、record_execution、release_unused、release_usage、故障/地点事件。库存耗尽、能力/权限、地点、版本冲突在后端复核；Agent 只获得快照。

单计划 holds 取最大值、耗材逐动作累加；跨患者通过同一资源 ID 排他分配，不能跨计划取 max 共享。M2 要求前序执行 accepted 且使用结束才能开始后序；这是串行研究计账规则，不是临床操作的时长或并行性结论。

旧 Runtime fixture 在 begin 时扣袋/包；M2-A 将预留、开始使用、按可信 receipt 实际计耗分开。两者不是同一生命周期接口，不能双扣或由 accepted 自动认定足量输注。消耗不回滚；未知回执隔离；设备停止/脱离/清理证据不足时继续占用，不能因计划数组结束就释放呼吸机。氧源/导管的 holds 分类也不证明临床可复用。

[src/core301/dispatch/shared_integration.py](../../src/core301/dispatch/shared_integration.py) 的 coordinator 将医疗资源与旧小队/车/接收容量一起核验；[src/core301/dispatch/service.py](../../src/core301/dispatch/service.py) 沿用该入口；[src/core301/dispatch/complete_contracts.py](../../src/core301/dispatch/complete_contracts.py) 保留所有动作、ID、scope 和依赖，禁止有损降回 V1。M2-C 共用 M2-A/B 状态，而非另起库存。`legacy_assets_disjoint` 必须由可信宿主说明，名字不同不证明物理资源独立；team_response 不会自动搬运新版设备。

证据：[tests/shared_resources/test_manager.py](../../tests/shared_resources/test_manager.py)、[tests/shared_dispatch/test_integration.py](../../tests/shared_dispatch/test_integration.py)、[tests/complete_dispatch/test_complete.py](../../tests/complete_dispatch/test_complete.py)；既有 [research_artifacts/resource_model_m2c/TEST_REPORT.md](../../research_artifacts/resource_model_m2c/TEST_REPORT.md) 记载45新测试+633回归，17个研究资源场景覆盖10单伤、5组合、2输血。均是本地管理器/Fixed或HTTP Mock验证，**无真实 LLM 或新合同 Pulse 执行**。

结论：研究映射 MATCHED，共享调度 PARTIAL（到预留及宿主驱动生命周期）；真实临床资源 UNVERIFIED；原生执行回执与共享账本的统一适配仍缺失。
