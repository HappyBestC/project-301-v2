# 301现有伤情与救助动作盘点（M1）

调查日期：2026-10-19（Asia/Shanghai）。仅只读调查与设计；“支持”指固定Profile下受限仿真工程准入，所有相关生产权限仍关闭，不表示真实医疗操作已验证。

## 1. 判定方法与范围

以已验收V2十类、V2.1五类基线及当前Registry交叉核对，不以旧模板、合同枚举或适配器能构造载荷代替正式准入。结果：12个正式受限业务动作，另有1个合同保留动作 inhaled_albuterol 未开放。V1八动作均包含在正式12动作中，没有额外遗漏。`action_id` 在本文是业务 action_type 标识；M2执行实例另用 action_instance_id，避免覆盖已有执行日志ID。

`remove_from_exposure`通过独立EvacuationPlan及复合伤bundle进入，不在V2通用TreatmentPlan枚举里；血胸在旧phase-1仍为reserved，但已由独立统一受限Registry正式纳入，不能误删。

## 2. V2.0十类正式配置与验证范围

源S01/S04/S06/S15；准确配置封存于基线，不取冻结版/v1里的同名“十类模板”替代。

| injury_type | 名称 | 固定严重度/位置 | 动作白名单（非任意组合） | 决策→终点/s |
|---|---|---|---|---|
| external_hemorrhage | 体表出血 | {"severity_levels": [0.4], "location": {"compartment": "RightLeg"}} | control_external_bleeding, fluid_resuscitation, transfusion | 180→480 |
| abdominal_internal_hemorrhage | 腹腔内出血 | {"severity_levels": [0.4], "location": {"compartment": "Spleen"}} | control_internal_bleeding, fluid_resuscitation, transfusion | 180→480 |
| open_pneumothorax | 开放性气胸 | {"severity_levels": [0.6], "location": {"side": "Left"}} | occlusive_dressing | 180→480 |
| closed_tension_pneumothorax | 闭合性张力性气胸 | {"severity_levels": [0.6], "location": {"side": "Left"}} | needle_decompression | 180→480 |
| respiratory_muscle_impairment | 呼吸肌功能受损 | {"severity_levels": [0.4], "location": {}} | intubation, mechanical_ventilation | 180→480 |
| impaired_alveolar_exchange | 肺泡气体交换受损 | {"severity_levels": [0.2, 0.4, 0.6], "location": {}} | supplemental_oxygen | 180→480 |
| dehydration | 脱水 | {"severity_levels": [0.2, 0.4, 0.6], "location": {}} | fluid_resuscitation | 180→480 |
| hemothorax | 血胸 | {"severity_levels": [0.8], "location": {"side": "Left"}} | control_hemothorax_bleeding, chest_tube | 660→960 |
| carbon_monoxide_exposure | CO 暴露 | {} | remove_from_exposure | 960→1860 |
| environmental_hypoxia | 环境低氧 | {} | remove_from_exposure | 360→660 |

CO环境固定CO=.005/O₂=.21；低氧固定CO=0/O₂=.12，撤离后均CO=0/O₂=.21；其余气体见动作表。旧七类健康60秒、伤情120秒、救助观测300秒；血胸健康60秒+伤情600秒；CO暴露900秒；环境低氧暴露300秒。以上是实验时序，不是临床操作时长。旧七类含13个历史配对配置，不能将三级Severity解释为0.2—0.6连续区间；统一基线的患者与状态身份由research_artifacts/v2_restricted_engineering_baseline_v1.0/VERSIONS.json及S04固定。

## 3. V2.1五类复合伤

S14与已封存FIVE_COMPOSITE_CONFIGURATIONS.json一致；仅正式AB序列，A/B/BA只是历史研究分支。组合中的动作能力不授权自由拼接新组合。

| pattern_id/名称 | 组件与固定参数 | AB顺序 | 决策→终点/s |
|---|---|---|---|
| penetrating_thoracic_composite_v2 / 胸部穿透性复合伤 | [{"injury_type": "open_pneumothorax", "severity": 0.6, "side": "Left"}, {"injury_type": "hemothorax", "severity": 0.8, "side": "Left"}] | occlusive_dressing → control_hemothorax_bleeding → chest_tube | 660→960 |
| blunt_thoracoabdominal_composite_v2 / 钝性胸腹复合伤 | [{"injury_type": "abdominal_internal_hemorrhage", "severity": 0.4, "compartment": "Spleen"}, {"injury_type": "closed_tension_pneumothorax", "severity": 0.6, "side": "Left"}] | control_internal_bleeding → fluid_resuscitation → needle_decompression | 180→480 |
| blast_hemorrhage_respiratory_composite_v2 / 爆炸致出血与呼吸功能障碍 | [{"injury_type": "external_hemorrhage", "severity": 0.4, "compartment": "RightLeg"}, {"injury_type": "respiratory_muscle_impairment", "severity": 0.4}] | control_external_bleeding → fluid_resuscitation → intubation → mechanical_ventilation | 180→480 |
| fire_co_alveolar_composite_v2 / 战场火灾与吸入性功能障碍 | [{"injury_type": "carbon_monoxide_exposure"}, {"injury_type": "impaired_alveolar_exchange", "severity": 0.4}] | remove_from_exposure → supplemental_oxygen | 960→1860 |
| trapped_hypoxia_dehydration_composite_v2 / 密闭空间受困复合伤 | [{"injury_type": "environmental_hypoxia"}, {"injury_type": "dehydration", "severity": 0.4}] | remove_from_exposure → fluid_resuscitation | 360→660 |

胸部组合血胸60秒、气胸540秒起病，其余起病/Condition初始化以S14及research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIXED_PROTOCOLS.md为准。源部位均固定；动作间.02秒只保证引擎生效顺序，不能作为多人协作耗时。复合伤已接受的残余低氧、呼吸急促、高钠等风险仍保留，不等于疗效/安全普遍成立。

## 4. 全动作清单

适用伤情列直接展开冻结配置；verified_scope继承第2、3节精确部位、级别、初始化和时窗，并受下列载荷限定。不得外推到另一侧、其他剂量或其他患者。

### `chest_tube` — 胸管引流

| 字段 | 核实结果 |
|---|---|
| action_id | chest_tube |
| action_name | 胸管引流 |
| applicable_injuries | 基础：hemothorax；复合：penetrating_thoracic_composite_v2 |
| pulse_implementation | TubeThoracostomy(Left, 30 mL/min) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 血胸控源后；660.02 s 提交、660.04 s 确认流量；复合伤遵循其独立时序；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S03/S06/S07；S01/S14/S15/S16/S27/S28 |

### `control_external_bleeding` — 体表出血源控制

| 字段 | 核实结果 |
|---|---|
| action_id | control_external_bleeding |
| action_name | 体表出血源控制 |
| applicable_injuries | 基础：external_hemorrhage；复合：blast_hemorrhage_respiratory_composite_v2 |
| pulse_implementation | Hemorrhage(Type=External, Compartment=RightLeg, Severity=0) |
| implementation_type | 后端研究代理 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 源身份、active/authorized 匹配；若同计划含支持治疗，先控源；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S04/S05；S01/S14/S15/S16/S27/S28 |

### `control_hemothorax_bleeding` — 血胸出血源控制

| 字段 | 核实结果 |
|---|---|
| action_id | control_hemothorax_bleeding |
| action_name | 血胸出血源控制 |
| applicable_injuries | 基础：hemothorax；复合：penetrating_thoracic_composite_v2 |
| pulse_implementation | Hemothorax(Side=Left, Severity=0) |
| implementation_type | 后端研究代理 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 同侧源控制先于胸管；连续会话及固定时序；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S06/S07；S01/S14/S15/S16/S27/S28 |

### `control_internal_bleeding` — 腹腔内出血源控制

| 字段 | 核实结果 |
|---|---|
| action_id | control_internal_bleeding |
| action_name | 腹腔内出血源控制 |
| applicable_injuries | 基础：abdominal_internal_hemorrhage；复合：blunt_thoracoabdominal_composite_v2 |
| pulse_implementation | Hemorrhage(Type=Internal, Compartment=Spleen, Severity=0) |
| implementation_type | 后端研究代理 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 同上；不是腹腔手术；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S04/S05；S01/S14/S15/S16/S27/S28 |

### `fluid_resuscitation` — 液体复苏

| 字段 | 核实结果 |
|---|---|
| action_id | fluid_resuscitation |
| action_name | 液体复苏 |
| applicable_injuries | 基础：external_hemorrhage, abdominal_internal_hemorrhage, dehydration；复合：blunt_thoracoabdominal_composite_v2, blast_hemorrhage_respiratory_composite_v2, trapped_hypoxia_dehydration_composite_v2 |
| pulse_implementation | SubstanceCompoundInfusion(Saline, 500 mL袋, 100 mL/min) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | iv_access；与输血互斥；出血计划同时控源时控源在先；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S02/S03/S08；S01/S14/S15/S16/S27/S28 |

### `intubation` — 气管插管

| 字段 | 核实结果 |
|---|---|
| action_id | intubation |
| action_name | 气管插管 |
| applicable_injuries | 基础：respiratory_muscle_impairment；复合：blast_hemorrhage_respiratory_composite_v2 |
| pulse_implementation | Intubation(Type=Tracheal) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | V2须与机械通气成对且在先，不单独扩展为通用气道适应证；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S02/S03/S04；S01/S14/S15/S16/S27/S28 |

### `mechanical_ventilation` — 机械通气

| 字段 | 核实结果 |
|---|---|
| action_id | mechanical_ventilation |
| action_name | 机械通气 |
| applicable_injuries | 基础：respiratory_muscle_impairment；复合：blast_hemorrhage_respiratory_composite_v2 |
| pulse_implementation | MechanicalVentilatorPressureControl：AssistedControl；FiO₂=.21；吸气压力13 cmH₂O；PEEP5 cmH₂O；12/min；吸气1 s；Slope .1 s |
| implementation_type | Pulse原生设备动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 插管在先；与补充氧冲突；持续设备支持；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S02/S03/S04；S01/S14/S15/S16/S27/S28 |

### `needle_decompression` — 针刺减压

| 字段 | 核实结果 |
|---|---|
| action_id | needle_decompression |
| action_name | 针刺减压 |
| applicable_injuries | 基础：closed_tension_pneumothorax；复合：blunt_thoracoabdominal_composite_v2 |
| pulse_implementation | NeedleDecompression(Left, On) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 匹配 Left 闭合张力性气胸；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S03/S07；S01/S14/S15/S16/S27/S28 |

### `occlusive_dressing` — 胸部封闭敷料

| 字段 | 核实结果 |
|---|---|
| action_id | occlusive_dressing |
| action_name | 胸部封闭敷料 |
| applicable_injuries | 基础：open_pneumothorax；复合：penetrating_thoracic_composite_v2 |
| pulse_implementation | ChestOcclusiveDressing(Left, On) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 匹配 Left 开放性气胸；复合伤仅固定AB；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S03/S07；S01/S14/S15/S16/S27/S28 |

### `remove_from_exposure` — 脱离暴露环境

| 字段 | 核实结果 |
|---|---|
| action_id | remove_from_exposure |
| action_name | 脱离暴露环境 |
| applicable_injuries | 基础：carbon_monoxide_exposure, environmental_hypoxia；复合：fire_co_alveolar_composite_v2, trapped_hypoxia_dehydration_composite_v2 |
| pulse_implementation | ChangeEnvironmentalConditions(CO=0, O₂=.21, CO₂=.0004, N₂余量) |
| implementation_type | 其他：原生环境修改 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | 受保护路径及接收环境凭据；匹配自有暴露分支；无位置移动或运输耗时模拟；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S07/S10；S01/S14/S15/S16/S27/S28 |

### `supplemental_oxygen` — 补充氧气

| 字段 | 核实结果 |
|---|---|
| action_id | supplemental_oxygen |
| action_name | 补充氧气 |
| applicable_injuries | 基础：impaired_alveolar_exchange；复合：fire_co_alveolar_composite_v2 |
| pulse_implementation | SupplementalOxygen(NasalCannula, .5 L/min, 425 L) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | V2肺泡固定范围或火灾AB；与插管/通气冲突；V1的NRB15 L/min不是V2协议；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S02/S04/S07；S01/S14/S15/S16/S27/S28 |

### `transfusion` — 输血

| 字段 | 核实结果 |
|---|---|
| action_id | transfusion |
| action_name | 输血 |
| applicable_injuries | 基础：external_hemorrhage, abdominal_internal_hemorrhage；复合：无正式AB |
| pulse_implementation | SubstanceCompoundInfusion(Blood, 500 mL袋, 100 mL/min) |
| implementation_type | Pulse原生动作 |
| verified_scope | 仅上述配置精确Profile；单伤情参数见第2节、复合伤见第3节；载荷如上。独立Soldier疗效研究不自动扩大Runtime准入。 |
| prerequisites | iv_access；与补液互斥；无已验收复合AB用血动作；另须原Runtime源身份、资源、会话与观察条件合法 |
| evidence | S02/S03/S08；S01/S14/S15/S16/S27/S28 |


### 合同保留项：`inhaled_albuterol`

S02有枚举，S04列为RESERVED_ACTIONS，V2 treatment_adapter明确拒绝。候选Albuterol吸入研究存在，但无正式准入Profile与已确认资源COSTS。不能将其列为第13个正式动作；为防遗漏，在映射表中单列UNKNOWN占位。Pulse内部呼吸操控/伤情注入/健康初始化不新增为业务救助动作。

## 5. Agent与已有资源接口

- 救助入口S21：`create_plan(context: AgentCaseContext) -> TreatmentPlan`；context为patient_id、known_injuries、patient_observation、available_resources；计划为patient_id及actions。V2手动provider见S22/S25；真实LLM规划不在十类/五类工程验收结论内。
- S13的ResourceState有8个非负计数：medic、surgery_team、airway_kit、iv_fluid_bag、chest_tube_kit、blood_unit、ventilator、ambulance。缺少位置、批次、技能、占用实例和鼻导管等细项，不能充当共享库存权威。
- 调度S23：异步`decide_dispatch(dispatch_input, query_eta) -> DispatchProposal`。S12输入包括run_id/patient_id、position、current_facility_id、patient_observation、treatment_plan及facilities/ambulances/medical_teams；输出patient_id、mode(onsite/team_response/evacuation)、team_id/ambulance_id/target_facility_id。
- Facility已有capacity、supported_action_types、reserved_patient_ids/admitted_patient_ids；MedicalTeam已有位置、supported_action_types与active_task_id；Ambulance有位置与active_task_id。S12的ActionType来自V1，不能直接接收12动作全部标识，需后续版本化桥接，M1不改合同。
- S08/S09以显式研究fixture管理stock、holds、permissions与单病例预留；S11复制HostResources，整体检查序列资源，数量按耗材累计、holds取序列最大值。patient_id绑定且不是多伤员总账。`medic=1`是研究占用令牌，不是某项医学资质证明；surgery_team字段存在不代表内出血动作真的执行手术。
- 暴露资源S10使用evacuation_teams与路径/接收环境布尔凭据；V2.1映射为evacuation_team占用。它们不是救护车轨迹或已验证MEDEVAC能力。
- MR5历史稿曾约定药品用品充足、人员不独立调度；本次用户明确要求扩展M1设计，因此无需改旧稿，也不把旧简化约定误认为本轮禁令。

## 6. 资料定位与疗效证据版本

《十类伤情和救助动作》《五类组合伤》《新版生理指标》三个精确题名文件未在项目文件名检索中找到；分别由B/TEN_INJURY_CONFIGURATIONS.json、C/FIVE_COMPOSITE_CONFIGURATIONS.json、research_artifacts/observation_v2_contract_freeze_v1.0/的正式档案提供对应材料。15指标档案自述USER_ACCEPTANCE_PENDING/NOT_ACTIVATED，不能宣称当前所有Runtime已使用新15指标。

已找到用户所述《Treatment Effect Rules V1.0 最终规则汇总表》（S18），其对应S17锁定的V2E-01—14。另有较早research_artifacts/treatment_effect_rules_v1.0_research_freeze中的R01—R14（10候选、4停用）；两者不能混称同一规则。本轮均保护，不替换、不重写阈值、不根据资源模型推导疗效。

S17定稿时“独立验证待完成”是历史状态；其后已有真实Pulse研究报告，不能用旧锁定结论否定后续实验。以下为本次查阅的后续报告索引（根R=research_artifacts/treatment_effect_rules_v2_candidate_v0.1）：

| 规则/动作 | 后续真实证据（R下） | M1引用边界 |
|---|---|---|
| 01外部停源、02/03支持 | pulse_validation_14_02_03_v1/PULSE_VALIDATION_RESULTS.md；pulse_validation_02_03_v1/PULSE_VALIDATION_RESULTS.md | RightLeg .4，既有zero源证据及后续支持分支；不修改规则 |
| 04/05/06腹腔停源、支持 | pulse_validation_04_05_06_v1/PULSE_VALIDATION_RESULTS.md | Soldier、Spleen .4；真实回执与原AST评价；安全UNRESOLVED |
| 07敷料 | pulse_validation_07_08_09_v2/PULSE_VALIDATION_RESULTS.md | 报告为P，08/09该批未启动，不能按批名推定都完成 |
| 08减压、09血胸联合 | pulse_validation_08_09_v1/PULSE_VALIDATION_RESULTS.md；pulse_validation_09_v1/PULSE_VALIDATION_RESULTS.md | 分批来源，另需区分机制、疗效与安全，不外推 |
| 10插管+通气 | pulse_validation_10_v1/PULSE_VALIDATION_RESULTS.md | Soldier、fatigue .4；真实设备支持，残余Tachypnea仍保留 |
| 11氧疗、13CO | pulse_validation_11_13_v1/PULSE_VALIDATION_RESULTS.md | 原预注册固定Profile；无临床认证 |
| 12脱水补液 | pulse_validation_12_recovery_v1/PULSE_VALIDATION_RESULTS.md | Condition .4、恢复证据、500 mL袋非实际全量入体 |
| 14低氧撤离 | pulse_validation_14_02_03_v1/PULSE_VALIDATION_RESULTS.md | 环境修改证据，不是运输模拟 |

本次未重算疗效、未跑Pulse；上述独立研究与B/C工程验收采用不同患者/证据链，不混合成新的验证范围。详尽原始轨迹及回执由各报告和S27/S28导航定位。

## 证据索引

所有 S 编号为本次读取的项目文件；CONFIRMED仅指所注明的工程事实。路径相对项目根，下面链接可直接打开。

| 编号 | 源文件 | 定位字段/符号 |
|---|---|---|
| S01 | [research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json](../../research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json) | profiles[].injury_type / actions / severity_levels / location / decision_s / end_s |
| S02 | [src/core301/contracts/v2/treatment.py](../../src/core301/contracts/v2/treatment.py) | ACTION_TYPES / CONFLICTS / TreatmentPlan.constraints |
| S03 | [src/core301/pulse/treatment_adapter.py](../../src/core301/pulse/treatment_adapter.py) | TreatmentAdapter.convert；V1载荷需结合V2覆盖 |
| S04 | [src/core301/pulse/v2/protocol_book.py](../../src/core301/pulse/v2/protocol_book.py) | OPEN_INJURIES / ALLOWED_ACTIONS / RESERVED_ACTIONS |
| S05 | [src/core301/pulse/v2/proxy_adapter.py](../../src/core301/pulse/v2/proxy_adapter.py) | ProxyAdapter.convert |
| S06 | [src/core301/runtime/v2/restricted_registry.py](../../src/core301/runtime/v2/restricted_registry.py) | REGISTRY；血胸/暴露独立受限准入 |
| S07 | [src/core301/runtime/v2_1/adapters.py](../../src/core301/runtime/v2_1/adapters.py) | action_payload / kinds_for |
| S08 | [src/core301/runtime/v2/resources.py](../../src/core301/runtime/v2/resources.py) | COSTS / ResearchResourceFixture / ResourceAuthority |
| S09 | [src/core301/runtime/v2/hemothorax_resources.py](../../src/core301/runtime/v2/hemothorax_resources.py) | COSTS / HemothoraxResources |
| S10 | [src/core301/contracts/v2/exposure_validation.py](../../src/core301/contracts/v2/exposure_validation.py) | EvacuationPlan / EvacuationResources |
| S11 | [src/core301/runtime/v2_1/resources.py](../../src/core301/runtime/v2_1/resources.py) | COSTS / Resources.reserve / begin / study_resources |
| S12 | [src/core301/dispatch/models.py](../../src/core301/dispatch/models.py) | Facility / MedicalTeam / Ambulance / DispatchInput / DispatchProposal |
| S13 | [src/core301/contracts/context.py](../../src/core301/contracts/context.py) | ResourceState / AgentCaseContext |
| S14 | [config/v2_1_battle_composite_patterns.yaml](../../config/v2_1_battle_composite_patterns.yaml) | patterns[].component_injuries / treatment_bundles / simulation_timeline |
| S15 | [research_artifacts/v2_restricted_engineering_baseline_v1.0/FIXED_PROTOCOLS.md](../../research_artifacts/v2_restricted_engineering_baseline_v1.0/FIXED_PROTOCOLS.md) | 固定范围、参数、时刻与初始化 |
| S16 | [research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIXED_PROTOCOLS.json](../../research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIXED_PROTOCOLS.json) | 实际原生动作、完成回执及资源记录 |
| S17 | [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/RULE_VERSION_MANIFEST.json](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/RULE_VERSION_MANIFEST.json) | 锁定研究规则版本 |
| S18 | [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_summary_v1/Treatment_Effect_Rules_V1.0_最终规则汇总表.md](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_summary_v1/Treatment_Effect_Rules_V1.0_最终规则汇总表.md) | V2E-01—14总表，非旧R01—R14 |
| S19 | [research_artifacts/observation_v2_contract_freeze_v1.0/README.md](../../research_artifacts/observation_v2_contract_freeze_v1.0/README.md) | 15指标工程冻结、尚未激活 |
| S20 | [MR5-资源字段与调度Agent输入输出.md](../../MR5-资源字段与调度Agent输入输出.md) | 历史设计稿，不等于当前完整实现 |
| S21 | [src/core301/agent/interface.py](../../src/core301/agent/interface.py) | TreatmentProvider.create_plan |
| S22 | [src/core301/agent/v2/manual_provider.py](../../src/core301/agent/v2/manual_provider.py) | ManualTreatmentProvider.create_plan |
| S23 | [src/core301/dispatch/providers.py](../../src/core301/dispatch/providers.py) | DispatchProvider.decide_dispatch |
| S24 | [src/core301/pulse/v2/exposure_session.py](../../src/core301/pulse/v2/exposure_session.py) | environment_action |
| S25 | [src/core301/contracts/v2/context.py](../../src/core301/contracts/v2/context.py) | AgentCaseContext |
| S26 | [src/core301/runtime/v2_1/contracts.py](../../src/core301/runtime/v2_1/contracts.py) | CompositePlan / HostResources |
| S27 | [research_artifacts/v2_restricted_engineering_baseline_v1.0/EVIDENCE_GUIDE.md](../../research_artifacts/v2_restricted_engineering_baseline_v1.0/EVIDENCE_GUIDE.md) | 历史原生配对、formal E2E与原始轨迹路径 |
| S28 | [research_artifacts/v2_1_restricted_engineering_baseline_v1.0/EVIDENCE_GUIDE.md](../../research_artifacts/v2_1_restricted_engineering_baseline_v1.0/EVIDENCE_GUIDE.md) | 复合伤历史比较及最终E2E证据 |

### 补充核对：后续疗效状态

pulse_validation_08_09_v1实际只完成08（P），09未启动；随后pulse_validation_09_v1完成09，并汇总14/14首轮AST输出为10 E、3 P、1 I。09的I由活动胸管瞬间流率缺测触发E1布尔失败，不能解释为证明治疗无效，也不等于14条医学验收通过。14早期报告的NOT_EVALUABLE为当时技术性拒绝，保留其历史语义，不覆盖后续报告。

S29补充：[`src/core301/pulse/v2/treatment_adapter.py`](../../src/core301/pulse/v2/treatment_adapter.py) 的TreatmentAdapter.convert明确覆盖鼻导管0.5 L/min、425 L，并拒绝phase-1保留动作；氧疗行证据还包括S29。
