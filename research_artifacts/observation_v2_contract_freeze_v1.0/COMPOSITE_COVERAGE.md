# 五类复合伤覆盖

| 复合伤 | 组成 | 候选 Agent 字段并集 | 额外内部观察 | 结论 |
|---|---|---|---|---|
| 胸部穿透性复合伤 | open_pneumothorax + hemothorax | 6 个主要字段去重，共用一份观察 | left_pleural_pressure_cmH2O, left_pleural_volume_mL, residual_blood_volume_mL, source_flow_mL_s, tube_flow_mL_min | 可复用，条件权限不自动合并授予 |
| 钝性胸腹复合伤 | abdominal_internal_hemorrhage + closed_tension_pneumothorax | 9 个主要字段去重，共用一份观察 | diagnostic.AbdominalCavityVolume, diagnostic.BloodVolume, diagnostic.TotalHemorrhageRate, left_pleural_pressure_cmH2O, left_pleural_volume_mL | 可复用，条件权限不自动合并授予 |
| 爆炸致出血与呼吸功能障碍 | external_hemorrhage + respiratory_muscle_impairment | 10 个主要字段去重，共用一份观察 | alveolar_ventilation_L_min, diagnostic.BloodVolume, diagnostic.TotalHemorrhageRate, diagnostic.TotalHemorrhagedVolume | 可复用，条件权限不自动合并授予 |
| 战场火灾与吸入性功能障碍 | carbon_monoxide_exposure + impaired_alveolar_exchange | 6 个主要字段去重，共用一份观察 | alveolar_ventilation_L_min, ambient_co_fraction, aorta_co_saturation, aorta_cohb_g_dL, oxygen_saturation | 可复用，条件权限不自动合并授予 |
| 密闭空间受困复合伤 | environmental_hypoxia + dehydration | 8 个主要字段去重，共用一份观察 | ambient_oxygen_fraction, aorta_sodium_mEq_L, diagnostic.BloodVolume, oxygen_saturation, total_fluid_mL | 可复用，条件权限不自动合并授予 |

30 条既有分支（每类 Control/A/B/AB/BA 加最终 Runtime AB）共 26710 个采样通过回放；25 组对照完成固定配置和治疗前状态匹配。两种伤情共用 HR/MAP/PaO₂，不重复记载；共享指标不提供伤情特异归因。血胸需引流/源和状态快照；CO 需 CO 负荷、氧合、PaCO₂/pH/Na 分开；脱水需容量、Na 和抗利尿；爆炸需通气和暂态事件。数据覆盖不等于已经形成有效性判定规则。
