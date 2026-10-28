# 十类基础伤情—指标映射（候选）

| injury_type | 主要指标（条件项仍须授权） | 辅助 / 安全 | 内部机制证据 | 来源及验证边界 |
|---|---|---|---|---|
| `external_hemorrhage` | 心率 HR、收缩压 SBP、平均动脉压 MAP、心输出量、血红蛋白浓度 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `diagnostic.TotalHemorrhageRate`、`diagnostic.TotalHemorrhagedVolume`、`diagnostic.BloodVolume`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `abdominal_internal_hemorrhage` | 心率 HR、收缩压 SBP、平均动脉压 MAP、心输出量、血红蛋白浓度 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `diagnostic.TotalHemorrhageRate`、`diagnostic.AbdominalCavityVolume`、`diagnostic.BloodVolume`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `open_pneumothorax` | 呼吸频率 RR、脉氧 SpO₂、动脉氧分压 PaO₂、潮气量 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `left_pleural_volume_mL`、`left_pleural_pressure_cmH2O`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `closed_tension_pneumothorax` | 呼吸频率 RR、脉氧 SpO₂、动脉氧分压 PaO₂、潮气量 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `left_pleural_volume_mL`、`left_pleural_pressure_cmH2O`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `hemothorax` | 脉氧 SpO₂、动脉氧分压 PaO₂、潮气量、平均动脉压 MAP、血红蛋白浓度 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `residual_blood_volume_mL`、`source_flow_mL_s`、`tube_flow_mL_min`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `respiratory_muscle_impairment` | 呼吸频率 RR、潮气量、动脉二氧化碳分压 PaCO₂、血液 pH、脉氧 SpO₂ | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `alveolar_ventilation_L_min`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `impaired_alveolar_exchange` | 脉氧 SpO₂、动脉氧分压 PaO₂、患者吸入氧浓度 FiO₂、动脉二氧化碳分压 PaCO₂、血液 pH | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `oxygen_saturation`、`alveolar_ventilation_L_min`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `dehydration` | 心率 HR、平均动脉压 MAP、心输出量、血红蛋白浓度、主动脉血钠浓度 | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `total_fluid_mL`、`diagnostic.BloodVolume`、`aorta_sodium_mEq_L`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `carbon_monoxide_exposure` | 主动脉碳氧血红蛋白浓度、动脉氧分压 PaO₂ | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `aorta_co_saturation`、`aorta_cohb_g_dL`、`oxygen_saturation`、`ambient_co_fraction`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |
| `environmental_hypoxia` | 脉氧 SpO₂、动脉氧分压 PaO₂、患者吸入氧浓度 FiO₂、心率 HR | 乳酸辅助；HR/MAP、PaCO₂/pH/Na 及原生事件按采集范围审查 | `ambient_oxygen_fraction`、`oxygen_saturation`；源快照/动作/事件分开 | 原生 DataRequest 见 metric_catalog；既有单伤及复合回放，缺口见报告 |

主要/辅助/安全分类不意味着效果阈值或自动因果归属。CO 的主要内部指标还包括 CO Saturation、模型 O₂ Saturation；PaO₂ 不能独自表示 CO 负荷。MAP/HR/PaO₂ 等共享量主要反映患者整体，不能在复合伤中单独归因于某一个伤情。所有完整映射字段、精确来源和层级见 metric_catalog.json。伤情输入参数和 Severity 不向 Agent 输出。
