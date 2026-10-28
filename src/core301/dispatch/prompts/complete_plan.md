M2-C 完整计划补充：本次 schema_version=301.dispatch.complete.1。
treatment_plan 使用301.treatment.complete.1，完整包含十二正式动作范围内已验证的序列。
三个control_*动作和remove_from_exposure不得删掉；它们分别是研究控源代理和环境移除，
不能解释为其他临床操作或已完成真实运输。不得增加inhaled_albuterol。
计划的动作ID、顺序、side/compartment、depends_on、范围和执行策略均为只读。
范围及severity是后端声明的固定研究配置，不允许由观察数据推断或改写隐藏伤情。
parameters由固定研究Profile定义，不得生成剂量/速度/设备设置覆盖。
机构和队伍的supported_action_types使用新版十二动作枚举，必须覆盖完整计划。
仍只输出原五字段DispatchProposal；不得返回治疗计划或伪造分配结果。
