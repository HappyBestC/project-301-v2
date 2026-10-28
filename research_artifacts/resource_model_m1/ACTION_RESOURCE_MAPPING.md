# 301救助动作—医疗能力—资源需求映射表

版本：M1设计V1.0，2026-10-19。正式12动作全部覆盖；另列1个未开放动作。S编号链接与符号见[盘点证据索引](CURRENT_ACTION_INVENTORY.md#证据索引)。本文是建模输入，不是医疗处置规范。

## 状态与证据口径

| 标记 | 含义 |
|---|---|
| CONFIRMED | 源码/已验收配置明确支持所述工程事实，或注明出处的已核对文献原则；不自动等于医学必要性已确认 |
| PROPOSED | 本轮提出的软件结构、资源分类或候选能力划分，尚未经项目确认 |
| PENDING_EXPERT_REVIEW | 具体医学操作的资质、必要设备/物料/设施等需专家核定 |
| UNKNOWN | 无足够证据；数量、时间等保留null（显示为待确认），不得当0或无限量 |

每一动作拆成“现有研究凭据”“拟议现实资源要求”，禁止给整行统一CONFIRMED后混入推测。`medic`、`iv_access`、`research_*`等工程令牌不是执业资格证明；研究包数量只适用于已有fixture。以下能力ID均为PROPOSED，保留12个动作级能力以避免把胸管引流和胸腔控源错误合并；界面可按出血、胸腔、气道、呼吸、输注、暴露六组展示。

## 全量动作与研究资源映射

stock为开始动作时扣减的研究库存；holds为研究序列占用的人员/设备令牌，并非现实物品可复用证明。数量逐项来自S08/S09/S11，不从医学常识补值。

| action_id/名称 | 医疗能力 | 研究stock | 研究holds | 研究权限 | 证据 |
|---|---|---|---|---|---|
| `chest_tube` / 胸管引流 | PROPOSED `pleural_drainage` | CONFIRMED chest_tube_kit×1 | CONFIRMED medic×1 | CONFIRMED research_chest_tube | S09/S11 |
| `control_external_bleeding` / 体表出血源控制 | PROPOSED `external_source_control` | CONFIRMED 研究配置无扣减项 | CONFIRMED medic×1 | CONFIRMED simulated_external_source_control | S08/S11 |
| `control_hemothorax_bleeding` / 血胸出血源控制 | PROPOSED `hemothorax_source_control` | CONFIRMED 研究配置无扣减项 | CONFIRMED medic×1 | CONFIRMED simulated_hemothorax_source_control | S09/S11 |
| `control_internal_bleeding` / 腹腔内出血源控制 | PROPOSED `internal_source_control` | CONFIRMED 研究配置无扣减项 | CONFIRMED medic×1 | CONFIRMED simulated_internal_source_control | S08/S11 |
| `fluid_resuscitation` / 液体复苏 | PROPOSED `iv_fluid_support` | CONFIRMED saline_500ml_bag×1 | CONFIRMED medic×1 | CONFIRMED iv_access | S08/S11 |
| `intubation` / 气管插管 | PROPOSED `tracheal_airway` | CONFIRMED airway_kit×1 | CONFIRMED medic×1 | CONFIRMED 无额外permission键；仍需capabilities含动作 | S08/S11 |
| `mechanical_ventilation` / 机械通气 | PROPOSED `ventilatory_support` | CONFIRMED 研究配置无扣减项 | CONFIRMED ventilator×1 | CONFIRMED 无额外permission键；仍需capabilities含动作 | S08/S11 |
| `needle_decompression` / 针刺减压 | PROPOSED `pleural_decompression` | CONFIRMED needle_kit×1 | CONFIRMED medic×1 | CONFIRMED 无额外permission键；仍需capabilities含动作 | S08/S11 |
| `occlusive_dressing` / 胸部封闭敷料 | PROPOSED `chest_wound_sealing` | CONFIRMED occlusive_dressing_kit×1 | CONFIRMED medic×1 | CONFIRMED 无额外permission键；仍需capabilities含动作 | S08/S11 |
| `remove_from_exposure` / 脱离暴露环境 | PROPOSED `exposure_removal` | CONFIRMED 研究配置无扣减项 | CONFIRMED evacuation_team×1 | CONFIRMED research_environment_removal | S10/S11 |
| `supplemental_oxygen` / 补充氧气 | PROPOSED `oxygen_delivery` | CONFIRMED 研究配置无扣减项 | CONFIRMED medic×1, nasal_cannula×1, oxygen_425l_source×1 | CONFIRMED 无额外permission键；仍需capabilities含动作 | S08/S11 |
| `transfusion` / 输血 | PROPOSED `blood_support` | CONFIRMED blood_500ml_bag×1 | CONFIRMED medic×1 | CONFIRMED iv_access | S08/S11 |

单伤情暴露S10名称为evacuation_teams，V2.1为evacuation_team；均要求数量可用及路径/接收环境凭据。研究库存以整袋/包计，不证明500 mL已全部输入，也未动态扣除425 L氧源。

## 现实需求候选与证据缺口（逐动作）

以下每行的临床必要性均PENDING_EXPERT_REVIEW；可追溯的工程存在性已在上表CONFIRMED。所有真实人员数、资源数量、操作时长均UNKNOWN/待确认；不以研究值填补。

### `chest_tube`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 胸管操作及持续管理人员技能；是否多人协作待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 引流装置、连接及监测配套作为候选；移动可用性依具体设备 |
| 药品耗材（PENDING_EXPERT_REVIEW） | chest_tube_kit研究扣减1；真实胸管/连接/收集部件和规格待核定 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 执行与持续引流的支持环境分别建模；地点条件未知，不能固定Role或医院 |
| 依赖表达（PROPOSED） | `pleural_drainage` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S09/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `control_external_bleeding`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 局部出血控制技能；自行/互救或专业人员的适用边界待核定 |
| 设备（PENDING_EXPERT_REVIEW） | 按实际术式选择压迫材料、敷料、止血器材；不能把研究停源默认为已使用止血带 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 器材类型、一次性/复用、用量及适用部位均待确认 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 现场能力组合候选；安全接近和暴露控制条件待确认；不能凭源Severity=0证明现场操作完成 |
| 依赖表达（PROPOSED） | `external_source_control` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `control_hemothorax_bleeding`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 胸部出血源处置资格、术式及团队待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 控源与引流是两个不同能力；胸管包不能代替控源资源 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 控源实际耗材未知；不能与chest_tube耗材合并抵扣 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 手术/其他控源条件待确认，不能从研究控源代理推断现场可施行 |
| 依赖表达（PROPOSED） | `hemothorax_source_control` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S09/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `control_internal_bleeding`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 内出血源控制所对应实际术式及专业团队构成待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 术式、手术/介入等资源路线未定义，不自动选一套设备 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 无可信物料清单；研究COSTS为空不代表现实零耗材 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 需哪些诊疗/操作/复苏条件待专家核定；不得简单绑定医院或把medic令牌视为手术能力 |
| 依赖表达（PROPOSED） | `internal_source_control` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `fluid_resuscitation`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 建立/维护血管通路及输注技能与协作要求待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 通路器材、输注组件候选；是否需要泵取决于实际方案，未确认 |
| 药品耗材（PENDING_EXPERT_REVIEW） | Saline 500 mL研究袋；真实补液种类/规格/数量、温控、有效期和兼容性待核定 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 按通路、物料和观察支持条件判定；不能把iv_access程序权限当成实际已建通路 |
| 依赖表达（PROPOSED） | `iv_fluid_support` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `intubation`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 气管插管资格、训练、协作及监测人员需求待确认 |
| 设备（PENDING_EXPERT_REVIEW） | airway_kit细项、喉镜、吸引和监测设备为待核查候选 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 气道耗材与可能药品由实际操作方案核定；不虚构镇静/镇痛药种类剂量 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 具备气道操作与持续支持条件的位置；具体环境、供电和备用方案待核定 |
| 依赖表达（PROPOSED） | `tracheal_airway` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `mechanical_ventilation`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 设备操作与持续监护的技能、人员配比待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 呼吸机可复用持续占用；移动型号、供电、气源/压缩气配置与回路依赖待核定 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 回路/过滤等配套候选；规格、消耗及更换条件待确认 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 现场/设施/途中均由具体设备和保障条件判断；当前研究并未验证途中通气 |
| 依赖表达（PROPOSED） | `ventilatory_support` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `needle_decompression`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 针刺减压的操作资质、训练与监督要求待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 减压器材规格、配套评估/监测要求待核定 |
| 药品耗材（PENDING_EXPERT_REVIEW） | needle_kit研究扣减1；实际针具类型、规格、数量不能由代码推定 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 地点按能否满足资质、无菌/操作及后续支持条件判断；哪些条件必要待核定 |
| 依赖表达（PROPOSED） | `pleural_decompression` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `occlusive_dressing`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 胸部伤口封闭处置技能/培训范围待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 拟将敷料包拆成规格化物料；额外设备是否必需未知 |
| 药品耗材（PENDING_EXPERT_REVIEW） | occlusive_dressing_kit研究一次性扣减；真实产品规格、数量、替换条件待确认 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 可建现场条件候选，不硬编码Role；接近伤员与后续观察条件待确认 |
| 依赖表达（PROPOSED） | `chest_wound_sealing` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `remove_from_exposure`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 安全脱离暴露的人员/团队技能、防护和人数待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 是否需要搬运器材、防护或车辆由路线与患者条件确定；未证实必需救护车 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 未定义实际防护/搬运物料，零研究stock不代表现实不消耗 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 当前已有protected_route_available与receiving_environment_verified凭据；M2拟增加位置和有效期；本动作不生成运输完成事实 |
| 依赖表达（PROPOSED） | `exposure_removal` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S10/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `supplemental_oxygen`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 氧疗实施与监测能力资格/人数待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 氧源与输送接口；鼻导管实际复用政策不可照抄fixture holds；减压/流量装置配套待核定 |
| 药品耗材（PENDING_EXPERT_REVIEW） | 氧气按体积连续消耗为PROPOSED；425 L仅固定仿真源参数，真实瓶型、剩余量和接口待确认 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 持续供氧、储存/运输与防护条件待核定；不预设现场不可用；非V2 NRB路线不作替代 |
| 依赖表达（PROPOSED） | `oxygen_delivery` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |

### `transfusion`

| 维度 | 需求及状态 |
|---|---|
| 人员（PENDING_EXPERT_REVIEW） | 输血实施、核对、监测与通路技能；资质和人数待确认 |
| 设备（PENDING_EXPERT_REVIEW） | 输注、检测/配血、储运及可能加温设备候选；是否必需逐项核定 |
| 药品耗材（PENDING_EXPERT_REVIEW） | Blood是仿真复合物；实际血液成分、血型兼容、批号、有效期与温控范围待确认 |
| 地点/设施（PENDING_EXPERT_REVIEW） | 供血/兼容性确认及储运保障条件需明确；不自动与Saline等价；不固定Role |
| 依赖表达（PROPOSED） | `blood_support` = 已核定技能/资格 AND 已选资源组合 AND 地点条件 AND 当前可用性；未知必要项导致INDETERMINATE，不宣称可用 |
| 数量/并发/时间（UNKNOWN） | 实际人员数、协作人数、库存用量、并发容量、准备/操作/监护/清理时间均待确认；重复分配须证明时间区间不重叠 |
| 依据/待补证 | S08/S11支持工程fixture；实际医学要求尚无逐项核定依据。查证任务见OPEN_QUESTIONS；AJP仅为组织建模依据，不证明本行动的具体资质/器械清单。 |


## 保留动作与替代关系

| action_id | 当前状态 | 能力与资源占位 | 处理 |
|---|---|---|---|
| inhaled_albuterol | CONFIRMED：合同保留、未开放（S02/S04） | PROPOSED：inhaled_drug_delivery；人员/设备/药耗/地点/数量均UNKNOWN | 不进入正式需求目录，不利用候选参数或临床常识自动放行 |

模型支持`alternatives`（OR），组合内`all_of`（AND）。本轮**没有确认任何现实资源组合可互相等效替代**。Saline/Blood是不同动作且现合同互斥；氧疗与通气不能作为通用替代；封闭敷料、减压、胸管及控源各自适用目标不同。不同厂家同类产品或移动/固定氧源的替代须有适用范围、接口兼容与医学证据；暂以空替代集表示，不自造OR。

## 从映射到资源数量的边界

1. 每个M1研究需求记录带`scope_kind=research_fixture`、profile引用和原COSTS来源，才能保留上述已知数量。真实需求记录独立标`clinical_design`且未知quantity=null，避免将研究一人令牌转成排班规范。
2. 人员、复用设备、设施床位使用时间区间；一次性包/袋按实际投入节点提交消耗；氧气等持续供应另计数量与流量。设备硬件与其消耗品不混成一个计数。
3. 研究整序列取holds最大值的做法只证明该序列实现，无跨伤员同时复用依据；M2按共享实体身份和有效时段检查。气道/通气支持结束之前不得因计划数组结束就释放呼吸机。
4. 环境移除、实际搬运、运输途中照护和到达交接是不同事实。M1预留TransportAsset关系，不把现有环境修改回执当成患者移动事件。
