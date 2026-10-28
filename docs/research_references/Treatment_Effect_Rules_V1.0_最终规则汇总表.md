# Treatment Effect Rules V1.0 最终规则汇总表

## 一、规则总体说明

可以把研究流程理解为：Agent根据伤情选择救助措施，Pulse模拟救治后的生理变化，再由对应规则判断疗效等级。本表说明评价规则，不表示已经接入真实Agent或完成新的独立实验。

- **E（有效）**：满足完整目标F。
- **P（部分有效）**：满足最低目标M，但没有满足F。
- **I（无效）**：数据可以评价，但没有满足最低目标M。
- **NOT_EVALUABLE（不可评价）**：必要证据缺失、数据异常、范围/动作/对照/时窗/授权或模式前提不足，无法可靠判定。不能把缺测直接判为I。
- **01、04仅有E/I，P不适用**。安全风险独立评价，不能被E覆盖。

**E代表该措施达到预定研究疗效目标，不代表伤员所有生理指标恢复正常，更不等于临床治愈。**

### 看表前的共同约定

“平均”指规定窗口采样值的均值；“全窗”指该窗口每个采样点都满足，不能用均值替代。除明确写“全部治疗后”的条件外，疗效指标使用**评价终点前最后60秒**。终点机制代理只在相应终点核验，模式资格使用治疗前读数。公共量采样步长1秒，胸腔压力/体积0.02秒，具体取点沿用原时间契约。“治疗前”是真实单点基线，不是假设的30点平均。“自身”比较治疗前与治疗后；Control为未治疗对照；zero为仅停止出血源的对照。

SpO₂以0～1比例保存；变化乘100后为**百分点**。PaO₂和PaCO₂单位mmHg，CO单位L/min。E始终包含最低目标M；下表P栏列出的均为“满足M且未达到E”的完整含义。所有行还须满足合法范围、执行、授权、单位、时间和相应必要机制/安全证据，不表示只看一个数值就能评分。

## 二、14条规则总览表

| 编号 | 伤情 | 救助动作 | 核心评价指标 | E：有效 | P：部分有效 | I：无效 |
| -- | -- | ---- | ------ | ---- | ------ | ---- |
| V2E-01 | 外部出血 | 停止出血源 | 累计失血量、总失血率 | 单一出血源身份确认；末60秒每个采样点的总失血率＝0 mL/s，累计失血量相对该窗口首点变化＝0 mL | 不适用 | 满足可评价条件，但未达到最低有效目标M |
| V2E-02 | 外部出血 | 停源后补液 | 心输出量CO | 满足最低目标M，且末60秒CO增量在每个采样点均≥6% | 停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-03 | 外部出血 | 停源后输血 | 心输出量CO | 满足最低目标M，且末60秒CO增量在每个采样点均≥6% | 停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-04 | 腹腔内出血 | 停止Spleen出血源 | 腹腔积血量、累计失血量、总失血率 | 单一出血源身份确认；末60秒每个采样点的总失血率＝0 mL/s，累计失血量相对该窗口首点变化＝0 mL，腹腔积血量相对该窗口首点变化＝0 mL | 不适用 | 满足可评价条件，但未达到最低有效目标M |
| V2E-05 | 腹腔内出血 | 停源后补液 | 心输出量CO | 满足最低目标M，且末60秒CO增量在每个采样点均≥5.5% | 停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-06 | 腹腔内出血 | 停源后输血 | 心输出量CO | 满足最低目标M，且末60秒CO增量在每个采样点均≥5.5% | 停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-07 | 开放性气胸 | 封闭敷料 | 平均动脉压MAP、动脉氧分压PaO₂、脉搏血氧SpO₂ | 满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；MAP全窗相对自身治疗前变化≥0 mmHg | 终点胸封通路阻断代理成立；末60秒相对未治疗Control，SpO₂平均高≥0.1个百分点，PaO₂平均高>0 mmHg；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-08 | 闭合性张力性气胸 | 针刺减压 | 平均动脉压MAP、动脉氧分压PaO₂、脉搏血氧SpO₂、左胸膜腔绝对压力、左胸膜腔气体体积 | 满足最低目标M，且两项距离全窗各缩短≥50%；自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；MAP全窗相对自身治疗前变化≥0 mmHg | 终点针刺通路通畅代理成立；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；压力和体积到各自匹配健康区间的距离，末60秒平均各缩短≥20%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-09 | 血胸 | 停源后胸管引流 | 动脉氧分压PaO₂、脉搏血氧SpO₂、潮气量VT、胸腔积血量 | 满足最低目标M；积血平均减少≥90%，全窗积血绝对值≤1 mL，原生自动停流证据成立；改善模式还需自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg，维持模式继续要求两项氧合全窗不降 | E1证据在查询前完整；积血相对治疗前平均减少≥20%；潮气量全窗≥治疗前的90%；同时满足所选氧合模式（改善模式：自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；维持模式：SpO₂和PaO₂全窗均不低于各自治疗前值）；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-10 | 呼吸肌功能受损 | 插管后机械通气 | 动脉二氧化碳分压PaCO₂、潮气量VT、实际患者PBW | 满足最低目标M；异常基线模式的距离全窗缩短≥50%，正常基线模式在区间内的采样比例＝100%；两种模式均需VT/PBW全窗在[4, 8] mL/kg内 | 原生通气支持确认；PaCO₂基线在[35, 45] mmHg外时，到区间距离平均缩短≥20%；基线已在区间内时，末窗在区间内的采样比例≥80%；两种模式均需末窗VT/PBW均值在[4, 8] mL/kg内；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-11 | 肺泡气体交换障碍 | 鼻导管吸氧 | 患者吸入氧比例FiO₂、动脉氧分压PaO₂、脉搏血氧SpO₂ | 满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg | 鼻导管供氧支持证据确认、末窗FiO₂为有限有效值；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-12 | 脱水 | 补液 | 血容量、心输出量CO、平均动脉压MAP、总体液体积 | 满足最低目标M；CO全窗增加≥5%，总体液和血容量全窗各增加≥100 mL；全窗残余体液缺口≤初始缺口的10%，且全窗总体液≤匹配健康300秒参考上端点 | 末60秒相对治疗前：CO平均增加≥2%，MAP平均变化≥0 mmHg，总体液和血容量平均各增加≥50 mL；同时平均体液缺口小于初始缺口；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-13 | 一氧化碳暴露 | 撤离CO环境 | 主动脉COHb质量浓度、环境CO比例、环境O₂比例 | 满足最低目标M，且末60秒COHb浓度下降比例全窗≥10% | 全部治疗后记录的环境CO＝0、环境O₂＝0.21（21%）；末60秒COHb相对自身治疗前的浓度下降比例平均≥5%；但未达到E | 满足可评价条件，但未达到最低有效目标M |
| V2E-14 | 环境低氧 | 恢复正常氧环境 | 动脉氧分压PaO₂、脉搏血氧SpO₂、环境CO比例、环境O₂比例 | 满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；目标低氧事件在末60秒不活跃 | 全部治疗后记录的环境CO＝0、环境O₂＝0.21（21%）；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；但未达到E | 满足可评价条件，但未达到最低有效目标M |

## 三、逐条规则详细说明

### V2E-01：外部出血—停止出血源

- **对应伤情**：外部出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。
- **救助措施**：按固定协议执行停止出血源；不改动作参数或时序。
- **评价目的**：判断固定出血源是否已经停止持续出血。
- **关键指标**：累计失血量（mL）；总失血率（mL/s）。
- **E判定**：需同时满足以下条件：单一出血源身份确认；末60秒每个采样点的总失血率＝0 mL/s，累计失血量相对该窗口首点变化＝0 mL。
- **P判定**：不适用，本条最低与完整目标相同。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：动作成功提交不等于已经止血。平台针对末窗内部变化，不要求累计失血总量归零，也不要求血容量恢复。只有同一合法单源时才能用总失血率作为源控制证据；未治疗Control仍须合法匹配供研究核查。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：看是否真正停止继续流血，而不是看已经流失的血是否自动补回来。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 单一出血源身份确认{single_source_identity_valid})`
- **模式资格**：`真`
- **最低目标M**：`(单一出血源身份确认{single_source_identity_valid} 且 逐点全部满足((W.rate ＝ 0{V2E-01.source_rate_target})) 且 逐点全部满足(((W.loss − 首点(W.loss)) ＝ 0{V2E-01.cumulative_change_target})))`
- **完整目标F**：`(单一出血源身份确认{single_source_identity_valid} 且 逐点全部满足((W.rate ＝ 0{V2E-01.source_rate_target})) 且 逐点全部满足(((W.loss − 首点(W.loss)) ＝ 0{V2E-01.cumulative_change_target})))`

</details>

### V2E-02：外部出血—停源后补液

- **对应伤情**：外部出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。
- **救助措施**：按固定协议执行停源后补液；不改动作参数或时序。
- **评价目的**：判断在已经停源之后，增加支持治疗是否进一步改善心脏泵血。
- **关键指标**：心输出量CO（L/min）。
- **E判定**：需同时满足以下条件：满足最低目标M，且末60秒CO增量在每个采样点均≥6%。
- **P判定**：需同时满足以下最低条件：停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：CO增量＝100×(治疗分支CO−仅停源zero分支CO)/共同治疗前CO。不是患者自身CO增长率。两分支须同患者、同初态、同出血源/Severity及时间，已停源后才评价支持治疗增量。MAP和Hb等风险/解释信息独立报告；不要求输血后Hb必然增加，也不把盐水稀释自动判为无效。补液和输血不能混用为同一分支；标称袋容量不等于实际入体量。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：这条规则比较额外补液与单纯止血，判断心脏泵血是否得到额外改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 匹配仅停源zero对照有效{matched_zero_valid} 且 补液/输血互斥约束有效{support_exclusivity_valid} 且 已停源背景成立{source_controlled_context_valid})`
- **模式资格**：`真`
- **最低目标M**：`(均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-02.co_min_pct})`
- **完整目标F**：`((均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-02.co_min_pct}) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO)) ≥ 6{V2E-02.co_full_pct})))`

</details>

### V2E-03：外部出血—停源后输血

- **对应伤情**：外部出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。
- **救助措施**：按固定协议执行停源后输血；不改动作参数或时序。
- **评价目的**：判断在已经停源之后，增加支持治疗是否进一步改善心脏泵血。
- **关键指标**：心输出量CO（L/min）。
- **E判定**：需同时满足以下条件：满足最低目标M，且末60秒CO增量在每个采样点均≥6%。
- **P判定**：需同时满足以下最低条件：停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：CO增量＝100×(治疗分支CO−仅停源zero分支CO)/共同治疗前CO。不是患者自身CO增长率。两分支须同患者、同初态、同出血源/Severity及时间，已停源后才评价支持治疗增量。MAP和Hb等风险/解释信息独立报告；不要求输血后Hb必然增加，也不把盐水稀释自动判为无效。补液和输血不能混用为同一分支；标称袋容量不等于实际入体量。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=RightLeg。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：这条规则比较额外输血与单纯止血，判断心脏泵血是否得到额外改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 匹配仅停源zero对照有效{matched_zero_valid} 且 补液/输血互斥约束有效{support_exclusivity_valid} 且 已停源背景成立{source_controlled_context_valid})`
- **模式资格**：`真`
- **最低目标M**：`(均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-03.co_min_pct})`
- **完整目标F**：`((均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-03.co_min_pct}) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO)) ≥ 6{V2E-03.co_full_pct})))`

</details>

### V2E-04：腹腔内出血—停止Spleen出血源

- **对应伤情**：腹腔内出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。
- **救助措施**：按固定协议执行停止Spleen出血源；不改动作参数或时序。
- **评价目的**：判断固定出血源是否已经停止持续出血。
- **关键指标**：腹腔积血量（mL）；累计失血量（mL）；总失血率（mL/s）。
- **E判定**：需同时满足以下条件：单一出血源身份确认；末60秒每个采样点的总失血率＝0 mL/s，累计失血量相对该窗口首点变化＝0 mL，腹腔积血量相对该窗口首点变化＝0 mL。
- **P判定**：不适用，本条最低与完整目标相同。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：动作成功提交不等于已经止血。平台针对末窗内部变化，不要求累计失血总量归零，也不要求血容量恢复。只有同一合法单源时才能用总失血率作为源控制证据；未治疗Control仍须合法匹配供研究核查。不把总失血率称为独立Spleen流率；腹腔积血平台不等于积血已清除。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：看是否真正停止继续流血，而不是看已经流失的血是否自动补回来。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 单一出血源身份确认{single_source_identity_valid})`
- **模式资格**：`真`
- **最低目标M**：`(单一出血源身份确认{single_source_identity_valid} 且 逐点全部满足((W.rate ＝ 0{V2E-04.source_rate_target})) 且 逐点全部满足(((W.loss − 首点(W.loss)) ＝ 0{V2E-04.cumulative_change_target})) 且 逐点全部满足(((W.abd − 首点(W.abd)) ＝ 0{V2E-04.abdominal_change_target})))`
- **完整目标F**：`(单一出血源身份确认{single_source_identity_valid} 且 逐点全部满足((W.rate ＝ 0{V2E-04.source_rate_target})) 且 逐点全部满足(((W.loss − 首点(W.loss)) ＝ 0{V2E-04.cumulative_change_target})) 且 逐点全部满足(((W.abd − 首点(W.abd)) ＝ 0{V2E-04.abdominal_change_target})))`

</details>

### V2E-05：腹腔内出血—停源后补液

- **对应伤情**：腹腔内出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。
- **救助措施**：按固定协议执行停源后补液；不改动作参数或时序。
- **评价目的**：判断在已经停源之后，增加支持治疗是否进一步改善心脏泵血。
- **关键指标**：心输出量CO（L/min）。
- **E判定**：需同时满足以下条件：满足最低目标M，且末60秒CO增量在每个采样点均≥5.5%。
- **P判定**：需同时满足以下最低条件：停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：CO增量＝100×(治疗分支CO−仅停源zero分支CO)/共同治疗前CO。不是患者自身CO增长率。两分支须同患者、同初态、同出血源/Severity及时间，已停源后才评价支持治疗增量。MAP和Hb等风险/解释信息独立报告；不要求输血后Hb必然增加，也不把盐水稀释自动判为无效。补液和输血不能混用为同一分支；标称袋容量不等于实际入体量。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：这条规则比较额外补液与单纯止血，判断心脏泵血是否得到额外改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 匹配仅停源zero对照有效{matched_zero_valid} 且 补液/输血互斥约束有效{support_exclusivity_valid} 且 已停源背景成立{source_controlled_context_valid})`
- **模式资格**：`真`
- **最低目标M**：`(均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-05.co_min_pct})`
- **完整目标F**：`((均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-05.co_min_pct}) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO)) ≥ 5.5{V2E-05.co_full_pct})))`

</details>

### V2E-06：腹腔内出血—停源后输血

- **对应伤情**：腹腔内出血；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。
- **救助措施**：按固定协议执行停源后输血；不改动作参数或时序。
- **评价目的**：判断在已经停源之后，增加支持治疗是否进一步改善心脏泵血。
- **关键指标**：心输出量CO（L/min）。
- **E判定**：需同时满足以下条件：满足最低目标M，且末60秒CO增量在每个采样点均≥5.5%。
- **P判定**：需同时满足以下最低条件：停源背景、匹配zero对照及补液/输血互斥合法；末60秒CO增量平均≥2%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：CO增量＝100×(治疗分支CO−仅停源zero分支CO)/共同治疗前CO。不是患者自身CO增长率。两分支须同患者、同初态、同出血源/Severity及时间，已停源后才评价支持治疗增量。MAP和Hb等风险/解释信息独立报告；不要求输血后Hb必然增加，也不把盐水稀释自动判为无效。补液和输血不能混用为同一分支；标称袋容量不等于实际入体量。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）；部位/侧别=Spleen。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：这条规则比较额外输血与单纯止血，判断心脏泵血是否得到额外改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 匹配仅停源zero对照有效{matched_zero_valid} 且 补液/输血互斥约束有效{support_exclusivity_valid} 且 已停源背景成立{source_controlled_context_valid})`
- **模式资格**：`真`
- **最低目标M**：`(均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-06.co_min_pct})`
- **完整目标F**：`((均值((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO))) ≥ 2{V2E-06.co_min_pct}) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((W.CO − C.CO) ÷ B.CO)) ≥ 5.5{V2E-06.co_full_pct})))`

</details>

### V2E-07：开放性气胸—封闭敷料

- **对应伤情**：开放性气胸；Profile `301.v2.phase1.research.1`；Severity=0.6（分档评价）；部位/侧别=Left。
- **救助措施**：按固定协议执行封闭敷料；不改动作参数或时序。
- **评价目的**：判断封闭敷料是否减轻相对未治疗的氧合恶化，并进一步区分是否达到自身恢复。
- **关键指标**：平均动脉压MAP（mmHg）；动脉氧分压PaO₂（mmHg）；脉搏血氧SpO₂（1）。
- **E判定**：需同时满足以下条件：满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；MAP全窗相对自身治疗前变化≥0 mmHg。
- **P判定**：需同时满足以下最低条件：终点胸封通路阻断代理成立；末60秒相对未治疗Control，SpO₂平均高≥0.1个百分点，PaO₂平均高>0 mmHg；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：左右侧和原生动作必须匹配。终点代理是既定原生通路状态证据，不是仅凭动作accepted；不能倒用于较早查询，也不证明全程漏气完全封闭。最低目标比较Control，完整目标另外要求自身改善。健康压力/体积距离不是本条主判定的必要条件，不能把注册表中的辅助参数擅自加到本条E/P门槛。自身氧合恶化、心动过速等须保留。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.6（分档评价）；部位/侧别=Left。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：比不处理恶化得少可以是部分有效；要达到有效，还必须看到患者自身氧合持续改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 伤情与动作侧别匹配{side_valid})`
- **模式资格**：`真`
- **最低目标M**：`(终点胸封阻断代理成立{endpoint_chest_seal_proxy} 且 (均值((100{unit.fraction_to_percent} × (W.SpO2 − C.SpO2))) ≥ 0.1{V2E-07.relative_SpO2_min_pp}) 且 (均值((W.PaO2 − C.PaO2)) > 0{V2E-07.relative_PaO2_min_mmHg}))`
- **完整目标F**：`((终点胸封阻断代理成立{endpoint_chest_seal_proxy} 且 (均值((100{unit.fraction_to_percent} × (W.SpO2 − C.SpO2))) ≥ 0.1{V2E-07.relative_SpO2_min_pp}) 且 (均值((W.PaO2 − C.PaO2)) > 0{V2E-07.relative_PaO2_min_mmHg})) 且 (((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-07.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-07.PaO2_delta_lower_mmHg})) 且 逐点全部满足(((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2)) ≥ 0.5{V2E-07.SpO2_full_pp})) 且 逐点全部满足(((W.PaO2 − B.PaO2) > 0{V2E-07.PaO2_delta_lower_mmHg}))) 且 逐点全部满足(((W.MAP − B.MAP) ≥ 0{V2E-07.complete_MAP_change_mmHg})))`

</details>

### V2E-08：闭合性张力性气胸—针刺减压

- **对应伤情**：闭合性张力性气胸；Profile `301.v2.phase1.research.1`；Severity=0.6（分档评价）；部位/侧别=Left。
- **救助措施**：按固定协议执行针刺减压；不改动作参数或时序。
- **评价目的**：判断固定针刺是否产生短期减压响应，同时改善氧合。
- **关键指标**：平均动脉压MAP（mmHg）；动脉氧分压PaO₂（mmHg）；脉搏血氧SpO₂（1）；左胸膜腔绝对压力（cmH2O）；左胸膜腔气体体积（mL）。
- **E判定**：需同时满足以下条件：满足最低目标M，且两项距离全窗各缩短≥50%；自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；MAP全窗相对自身治疗前变化≥0 mmHg。
- **P判定**：需同时满足以下最低条件：终点针刺通路通畅代理成立；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；压力和体积到各自匹配健康区间的距离，末60秒平均各缩短≥20%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：压力为绝对压力cmH2O，不是表压；体积为mL。距离d(x,[L,U])＝max(L−x,0,x−U)，缩短率＝100×(治疗前距离−当前距离)/治疗前距离。每项指标若基线距离为0，分别改为该指标全窗保持区间内，不计算缩短率、不加epsilon。健康包络只适用于匹配患者/引擎/环境；按既定政策只加一次容限。要求20%/50%距离缩短不等于必须完全回到健康区间；针刺代理不证明原发漏气源修复或长期不复发。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.6（分档评价）；部位/侧别=Left。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：不仅看血氧，也看胸腔压力和体积是否向这个患者自己的健康参考靠近。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 伤情与动作侧别匹配{side_valid})`
- **模式资格**：`真`
- **最低目标M**：`(终点针刺通路通畅代理成立{endpoint_needle_patent_proxy} 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-08.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-08.PaO2_delta_lower_mmHg})) 且 若((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero})))否则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) − 距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range})) ÷ 距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range})))) ≥ 20{V2E-08.mechanism_min_distance_reduction_pct})) 且 若((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero})))否则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) − 距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range})) ÷ 距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range})))) ≥ 20{V2E-08.mechanism_min_distance_reduction_pct})))`
- **完整目标F**：`((终点针刺通路通畅代理成立{endpoint_needle_patent_proxy} 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-08.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-08.PaO2_delta_lower_mmHg})) 且 若((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero})))否则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) − 距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range})) ÷ 距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range})))) ≥ 20{V2E-08.mechanism_min_distance_reduction_pct})) 且 若((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero})))否则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) − 距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range})) ÷ 距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range})))) ≥ 20{V2E-08.mechanism_min_distance_reduction_pct}))) 且 (((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-08.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-08.PaO2_delta_lower_mmHg})) 且 逐点全部满足(((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2)) ≥ 0.5{V2E-08.SpO2_full_pp})) 且 逐点全部满足(((W.PaO2 − B.PaO2) > 0{V2E-08.PaO2_delta_lower_mmHg}))) 且 若((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) ＝ 0{constant.zero})))否则(逐点全部满足(((100{unit.fraction_to_percent} × ((距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}) − 距区间距离(H.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range})) ÷ 距区间距离(B.pressure, [1024.4718877946036, 1029.796423698125]{reference.pressure_final_range}))) ≥ 50{V2E-08.mechanism_full_distance_reduction_pct}))) 且 若((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero}))则(逐点全部满足((距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) ＝ 0{constant.zero})))否则(逐点全部满足(((100{unit.fraction_to_percent} × ((距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}) − 距区间距离(H.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range})) ÷ 距区间距离(B.volume, [948.3006123152339, 1450.6802880244936]{reference.volume_final_range}))) ≥ 50{V2E-08.mechanism_full_distance_reduction_pct}))) 且 逐点全部满足(((W.MAP − B.MAP) ≥ 0{V2E-08.complete_MAP_change_mmHg})))`

</details>

### V2E-09：血胸—停源后胸管引流

- **对应伤情**：血胸；Profile `301.v2.hemothorax.restricted.1`；Severity=0.8（分档评价）；部位/侧别=Left。
- **救助措施**：按固定协议执行停源后胸管引流；不改动作参数或时序。
- **评价目的**：判断联合救助是否减少胸腔积血，并兼顾呼吸改善或原有氧合水平的维持。
- **关键指标**：动脉氧分压PaO₂（mmHg）；脉搏血氧SpO₂（1）；潮气量VT（mL）；胸腔积血量（mL）。
- **E判定**：需同时满足以下条件：满足最低目标M；积血平均减少≥90%，全窗积血绝对值≤1 mL，原生自动停流证据成立；改善模式还需自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg，维持模式继续要求两项氧合全窗不降。
- **P判定**：需同时满足以下最低条件：E1证据在查询前完整；积血相对治疗前平均减少≥20%；潮气量全窗≥治疗前的90%；同时满足所选氧合模式（改善模式：自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；维持模式：SpO₂和PaO₂全窗均不低于各自治疗前值）；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：只评价“停源→胸管引流”整链，不拆成独立胸管疗效。维持模式资格：治疗前SpO₂在[0.94,0.98]（94%～98%）且PaO₂在[75,100] mmHg，两区间均含端点；改善模式资格：至少一项低于其下界，且两项都不超过各自上界。其他高值或混合高低组合为NOT_EVALUABLE。维持模式的SpO₂/PaO₂允许下降预算均为0。积血减少率＝100×(治疗前积血−当前积血)/治疗前积血；基线必须支持合法计算。原始负残值保留，以绝对值核对≤1 mL，不裁剪、不补零、不凭缺失流率积分。E1是工程机制证据名称，不是E等级；其可用时刻不得晚于查询。 固定研究配置：Profile `301.v2.hemothorax.restricted.1`；Severity=0.8（分档评价）；部位/侧别=Left。计划救助时刻660秒、评价终点960秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：原本缺氧就要看改善；原本氧合处于规定区间，则要求引流过程中不把氧合弄差。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid} 且 伤情与动作侧别匹配{side_valid})`
- **模式资格**：`((在闭区间内(B.SpO2, [0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}) 且 在闭区间内(B.PaO2, [75, 100]{V2E-09.maintenance_baseline_PaO2_range})) 或 (((B.SpO2 < 取元素([0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}, 0{index.lower})) 或 (B.PaO2 < 取元素([75, 100]{V2E-09.maintenance_baseline_PaO2_range}, 0{index.lower}))) 且 (B.SpO2 ≤ 取元素([0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}, 1{index.upper})) 且 (B.PaO2 ≤ 取元素([75, 100]{V2E-09.maintenance_baseline_PaO2_range}, 1{index.upper}))))`
- **最低目标M**：`((查询前E1机制证据完整{E1_complete} 且 (均值((100{unit.fraction_to_percent} × ((B.blood − W.blood) ÷ B.blood))) ≥ 20{V2E-09.volume_reduction_min_pct})) 且 逐点全部满足((W.VT ≥ (0.9{V2E-09.tidal_volume_floor_fraction_B} × B.VT))) 且 若((在闭区间内(B.SpO2, [0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}) 且 在闭区间内(B.PaO2, [75, 100]{V2E-09.maintenance_baseline_PaO2_range})))则((逐点全部满足(((W.SpO2 − B.SpO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_SpO2_drop_budget}))) 且 逐点全部满足(((W.PaO2 − B.PaO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_PaO2_drop_budget})))))否则(((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-09.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-09.PaO2_delta_lower_mmHg}))))`
- **完整目标F**：`(((查询前E1机制证据完整{E1_complete} 且 (均值((100{unit.fraction_to_percent} × ((B.blood − W.blood) ÷ B.blood))) ≥ 20{V2E-09.volume_reduction_min_pct})) 且 逐点全部满足((W.VT ≥ (0.9{V2E-09.tidal_volume_floor_fraction_B} × B.VT))) 且 若((在闭区间内(B.SpO2, [0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}) 且 在闭区间内(B.PaO2, [75, 100]{V2E-09.maintenance_baseline_PaO2_range})))则((逐点全部满足(((W.SpO2 − B.SpO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_SpO2_drop_budget}))) 且 逐点全部满足(((W.PaO2 − B.PaO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_PaO2_drop_budget})))))否则(((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-09.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-09.PaO2_delta_lower_mmHg})))) 且 (查询前E1机制证据完整{E1_complete} 且 ((均值((100{unit.fraction_to_percent} × ((B.blood − W.blood) ÷ B.blood))) ≥ 20{V2E-09.volume_reduction_min_pct}) 且 (均值((100{unit.fraction_to_percent} × ((B.blood − W.blood) ÷ B.blood))) ≥ 90{V2E-09.volume_reduction_full_pct}) 且 逐点全部满足((绝对值(W.blood) ≤ 1{V2E-09.residual_abs_max_mL})) 且 原生自动停流确认{native_auto_stop_confirmed})) 且 若((在闭区间内(B.SpO2, [0.94, 0.98]{V2E-09.maintenance_baseline_SpO2_range}) 且 在闭区间内(B.PaO2, [75, 100]{V2E-09.maintenance_baseline_PaO2_range})))则((逐点全部满足(((W.SpO2 − B.SpO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_SpO2_drop_budget}))) 且 逐点全部满足(((W.PaO2 − B.PaO2) ≥ (-1{constant.minus_one} × 0{V2E-09.maintenance_PaO2_drop_budget})))))否则((((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-09.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-09.PaO2_delta_lower_mmHg})) 且 逐点全部满足(((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2)) ≥ 0.5{V2E-09.SpO2_full_pp})) 且 逐点全部满足(((W.PaO2 − B.PaO2) > 0{V2E-09.PaO2_delta_lower_mmHg})))))`

</details>

### V2E-10：呼吸肌功能受损—插管后机械通气

- **对应伤情**：呼吸肌功能受损；Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）。
- **救助措施**：按固定协议执行插管后机械通气；不改动作参数或时序。
- **评价目的**：判断机械通气是否改善或维持二氧化碳排出，同时提供规定范围的潮气量。
- **关键指标**：动脉二氧化碳分压PaCO₂（mmHg）；潮气量VT（mL）；实际患者PBW（kg）。
- **E判定**：需同时满足以下条件：满足最低目标M；异常基线模式的距离全窗缩短≥50%，正常基线模式在区间内的采样比例＝100%；两种模式均需VT/PBW全窗在[4, 8] mL/kg内。
- **P判定**：需同时满足以下最低条件：原生通气支持确认；PaCO₂基线在[35, 45] mmHg外时，到区间距离平均缩短≥20%；基线已在区间内时，末窗在区间内的采样比例≥80%；两种模式均需末窗VT/PBW均值在[4, 8] mL/kg内；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：必须是插管→机械通气整链，插管单独不能判有效。PaCO₂区间含端点，距离计算与08同义；基线正常时采用维持条件，不要求继续降低PaCO₂。VT为潮气量mL，PBW为按实际患者性别/身高得到的预测体重kg，不是实测体重，也不能统一写死为75.3kg。pH、过高/过低PaCO₂等安全异常独立保留；机械通气补偿不等于呼吸肌恢复。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.4（分档评价）。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：既要看二氧化碳是否向目标范围靠近，也要看每次送入的气量是否适合这个患者。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid})`
- **模式资格**：`真`
- **最低目标M**：`(原生通气支持确认{ventilation_support_confirmed} 且 若((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) > 0{constant.zero}))则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) − 距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg})) ÷ 距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg})))) ≥ 20{V2E-10.distance_reduction_min_pct}))否则((均值((距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) ＝ 0{constant.zero})) ≥ 0.8{V2E-10.maintenance_fraction_min})) 且 在闭区间内(均值((W.VT ÷ 实际患者PBW(kg){patient_PBW_kg})), [4, 8]{V2E-10.VT_PBW_mL_kg}))`
- **完整目标F**：`((原生通气支持确认{ventilation_support_confirmed} 且 若((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) > 0{constant.zero}))则((均值((100{unit.fraction_to_percent} × ((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) − 距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg})) ÷ 距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg})))) ≥ 20{V2E-10.distance_reduction_min_pct}))否则((均值((距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) ＝ 0{constant.zero})) ≥ 0.8{V2E-10.maintenance_fraction_min})) 且 在闭区间内(均值((W.VT ÷ 实际患者PBW(kg){patient_PBW_kg})), [4, 8]{V2E-10.VT_PBW_mL_kg})) 且 若((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) > 0{constant.zero}))则(逐点全部满足(((100{unit.fraction_to_percent} × ((距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) − 距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg})) ÷ 距区间距离(B.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}))) ≥ 50{V2E-10.distance_reduction_full_pct})))否则((均值((距区间距离(W.PaCO2, [35, 45]{V2E-10.PaCO2_target_mmHg}) ＝ 0{constant.zero})) ＝ 1{V2E-10.maintenance_fraction_full})) 且 逐点全部满足(在闭区间内((W.VT ÷ 实际患者PBW(kg){patient_PBW_kg}), [4, 8]{V2E-10.VT_PBW_mL_kg})))`

</details>

### V2E-11：肺泡气体交换障碍—鼻导管吸氧

- **对应伤情**：肺泡气体交换障碍；Profile `301.v2.phase1.research.1`；Severity=0.2/0.4/0.6（分档评价）。
- **救助措施**：按固定协议执行鼻导管吸氧；不改动作参数或时序。
- **评价目的**：判断固定氧疗是否带来可持续的自身氧合改善。
- **关键指标**：患者吸入氧比例FiO₂（1）；动脉氧分压PaO₂（mmHg）；脉搏血氧SpO₂（1）。
- **E判定**：需同时满足以下条件：满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg。
- **P判定**：需同时满足以下最低条件：鼻导管供氧支持证据确认、末窗FiO₂为有限有效值；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：Severity=0.2、0.4、0.6分别评价，不能混合比较；动作按既定固定氧疗协议，不引入新剂量。环境O₂比例、患者FiO₂、SpO₂、PaO₂是不同字段；FiO₂有效值不等于氧合改善。PaCO₂上升、pH下降与原生异常独立保留，不能仅凭SpO₂改善判定整体安全。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.2/0.4/0.6（分档评价）。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：吸上氧只是动作完成，还要看患者血氧和动脉氧分压是否真的改善。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid})`
- **模式资格**：`真`
- **最低目标M**：`((鼻导管供氧支持确认{oxygen_support_confirmed} 且 均为有限值(W.FiO2)) 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-11.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-11.PaO2_delta_lower_mmHg})))`
- **完整目标F**：`(((鼻导管供氧支持确认{oxygen_support_confirmed} 且 均为有限值(W.FiO2)) 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-11.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-11.PaO2_delta_lower_mmHg}))) 且 (((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-11.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-11.PaO2_delta_lower_mmHg})) 且 逐点全部满足(((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2)) ≥ 0.5{V2E-11.SpO2_full_pp})) 且 逐点全部满足(((W.PaO2 − B.PaO2) > 0{V2E-11.PaO2_delta_lower_mmHg}))))`

</details>

### V2E-12：脱水—补液

- **对应伤情**：脱水；Profile `301.v2.phase1.research.1`；Severity=0.2/0.4/0.6（分档评价）。
- **救助措施**：按固定协议执行补液；不改动作参数或时序。
- **评价目的**：判断补液后的循环及容量恢复，而不是把容量恢复和电解质纠正合成一个结论。
- **关键指标**：血容量（mL）；心输出量CO（L/min）；平均动脉压MAP（mmHg）；总体液体积（mL）。
- **E判定**：需同时满足以下条件：满足最低目标M；CO全窗增加≥5%，总体液和血容量全窗各增加≥100 mL；全窗残余体液缺口≤初始缺口的10%，且全窗总体液≤匹配健康300秒参考上端点。
- **P判定**：需同时满足以下最低条件：末60秒相对治疗前：CO平均增加≥2%，MAP平均变化≥0 mmHg，总体液和血容量平均各增加≥50 mL；同时平均体液缺口小于初始缺口；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：三档Severity分别评价。H0为匹配健康0秒总体液，H1为匹配健康300秒上端点；初始缺口D0=H0−治疗前总体液必须>0，否则不具备本规则模式资格；D(t)=H0−当前总体液。H0/H1是同患者合法参考，不是通用正常范围，不能用体液质量kg代替体积mL。Na属于必要安全观察，容量疗效不包含高钠已纠正的结论。保留原有异常、新发异常和自身/Control差异。 固定研究配置：Profile `301.v2.phase1.research.1`；Severity=0.2/0.4/0.6（分档评价）。计划救助时刻180秒、评价终点480秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：补液让循环和体液好转，不代表血钠异常也已经解决。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid})`
- **模式资格**：`((匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − B.fluid) > 0{constant.zero})`
- **最低目标M**：`(((均值((100{unit.fraction_to_percent} × ((W.CO − B.CO) ÷ B.CO))) ≥ 2{V2E-12.co_min_self_pct}) 且 (均值((W.MAP − B.MAP)) ≥ 0{V2E-12.MAP_min_mean_change_mmHg}) 且 (均值((W.fluid − B.fluid)) ≥ 50{V2E-12.fluid_min_increase_mL}) 且 (均值((W.BV − B.BV)) ≥ 50{V2E-12.blood_volume_min_increase_mL})) 且 (均值((匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − W.fluid)) < (匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − B.fluid)))`
- **完整目标F**：`((((均值((100{unit.fraction_to_percent} × ((W.CO − B.CO) ÷ B.CO))) ≥ 2{V2E-12.co_min_self_pct}) 且 (均值((W.MAP − B.MAP)) ≥ 0{V2E-12.MAP_min_mean_change_mmHg}) 且 (均值((W.fluid − B.fluid)) ≥ 50{V2E-12.fluid_min_increase_mL}) 且 (均值((W.BV − B.BV)) ≥ 50{V2E-12.blood_volume_min_increase_mL})) 且 (均值((匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − W.fluid)) < (匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − B.fluid))) 且 (((均值((100{unit.fraction_to_percent} × ((W.CO − B.CO) ÷ B.CO))) ≥ 2{V2E-12.co_min_self_pct}) 且 (均值((W.MAP − B.MAP)) ≥ 0{V2E-12.MAP_min_mean_change_mmHg}) 且 (均值((W.fluid − B.fluid)) ≥ 50{V2E-12.fluid_min_increase_mL}) 且 (均值((W.BV − B.BV)) ≥ 50{V2E-12.blood_volume_min_increase_mL})) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((W.CO − B.CO) ÷ B.CO)) ≥ 5{V2E-12.co_full_self_pct})) 且 逐点全部满足(((W.fluid − B.fluid) ≥ 100{V2E-12.fluid_full_increase_mL})) 且 逐点全部满足(((W.BV − B.BV) ≥ 100{V2E-12.blood_volume_full_increase_mL}))) 且 逐点全部满足(((匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − W.fluid) ≤ (0.1{V2E-12.residual_fraction_of_initial_deficit} × (匹配健康0秒总体液H0(mL){matched_healthy_total_fluid_mL} − B.fluid)))) 且 逐点全部满足((W.fluid ≤ 匹配健康300秒总体液H1(mL){matched_healthy_total_fluid_upper_mL})))`

</details>

### V2E-13：一氧化碳暴露—撤离CO环境

- **对应伤情**：一氧化碳暴露；Profile `301.v2.co.removal.restricted.1`；伤情环境CO=0.005、O₂=0.21。
- **救助措施**：按固定协议执行撤离CO环境；不改动作参数或时序。
- **评价目的**：判断CO环境暴露停止之后，患者体内COHb负荷是否下降。
- **关键指标**：主动脉COHb质量浓度（g/dL）；环境CO比例（1）；环境O₂比例（1）。
- **E判定**：需同时满足以下条件：满足最低目标M，且末60秒COHb浓度下降比例全窗≥10%。
- **P判定**：需同时满足以下最低条件：全部治疗后记录的环境CO＝0、环境O₂＝0.21（21%）；末60秒COHb相对自身治疗前的浓度下降比例平均≥5%；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：COHb是Aorta COHb质量浓度g/dL，不是COHb饱和百分比。下降比例＝100×(治疗前浓度−当前浓度)/治疗前浓度；合法分母和轨迹必需。环境CO清零不等于体内COHb清零，达到10%下降不代表完全清除；PaO₂升高不是本规则E/P的必要条件。环境条件检查全部POST，不仅末60秒；高钠等安全异常继续保留。 固定研究配置：Profile `301.v2.co.removal.restricted.1`；伤情环境CO=0.005、O₂=0.21。计划救助时刻960秒、评价终点1860秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：先确认不再继续吸入CO，再看体内CO负荷是否确实下降。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid})`
- **模式资格**：`真`
- **最低目标M**：`((逐点全部满足((POST.ambientCO ＝ 0{V2E-13.ambientCO_target})) 且 逐点全部满足((POST.ambientO2 ＝ 0.21{V2E-13.ambientO2_target}))) 且 (均值((100{unit.fraction_to_percent} × ((B.COHb − W.COHb) ÷ B.COHb))) ≥ 5{V2E-13.COHb_min_drop_pct}))`
- **完整目标F**：`(((逐点全部满足((POST.ambientCO ＝ 0{V2E-13.ambientCO_target})) 且 逐点全部满足((POST.ambientO2 ＝ 0.21{V2E-13.ambientO2_target}))) 且 (均值((100{unit.fraction_to_percent} × ((B.COHb − W.COHb) ÷ B.COHb))) ≥ 5{V2E-13.COHb_min_drop_pct})) 且 逐点全部满足(((100{unit.fraction_to_percent} × ((B.COHb − W.COHb) ÷ B.COHb)) ≥ 10{V2E-13.COHb_full_drop_pct})))`

</details>

### V2E-14：环境低氧—恢复正常氧环境

- **对应伤情**：环境低氧；Profile `301.v2.hypoxia.removal.restricted.1`；伤情环境CO=0、O₂=0.12。
- **救助措施**：按固定协议执行恢复正常氧环境；不改动作参数或时序。
- **评价目的**：判断正常氧环境恢复后，患者氧合是否改善且目标低氧事件是否解除。
- **关键指标**：动脉氧分压PaO₂（mmHg）；脉搏血氧SpO₂（1）；环境CO比例（1）；环境O₂比例（1）。
- **E判定**：需同时满足以下条件：满足最低目标M，且自身SpO₂全窗增加≥0.5个百分点，且自身PaO₂全窗增加>0 mmHg；目标低氧事件在末60秒不活跃。
- **P判定**：需同时满足以下最低条件：全部治疗后记录的环境CO＝0、环境O₂＝0.21（21%）；自身SpO₂平均增加≥0.1个百分点，且自身PaO₂平均增加>0 mmHg；但未达到上述完整E条件。
- **I判定**：满足可评价条件，但未达到最低有效目标M。必要数据不足或前置条件不成立应为NOT_EVALUABLE。
- **特殊说明**：环境氧恢复、患者FiO₂、SpO₂和PaO₂不能混为一谈。环境条件检查全部POST；低氧目标事件检查末窗。早期Hypoxia、Tachycardia及其他原生异常完整保留，末窗解除不能抹去早期风险。合法匹配Control用于独立比较，不改变本条自身氧合判定基准。 固定研究配置：Profile `301.v2.hypoxia.removal.restricted.1`；伤情环境CO=0、O₂=0.12。计划救助时刻360秒、评价终点660秒，主评价为末60秒；动作时间仍以原生回执核验。

**通俗理解：空气恢复正常还不够，还要看到患者血氧改善，并核对低氧事件是否仍在持续。**

<details>
<summary>研发核对：源AST逐项展开（读者可跳过）</summary>

B＝治疗前单点，W＝末60秒公共量，H＝末60秒高频胸腔量，C＝同窗对照，POST＝全部治疗后；变量单位同上。花括号标注原参数/证据名称。

- **前置条件**：`(固定研究范围合法{scope_valid} 且 原生救助执行证据合法{execution_valid} 且 所需研究数据/执行授权合法{authorization_valid})`
- **模式资格**：`真`
- **最低目标M**：`((逐点全部满足((POST.ambientO2 ＝ 0.21{V2E-14.ambientO2_target})) 且 逐点全部满足((POST.ambientCO ＝ 0{V2E-14.ambientCO_target}))) 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-14.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-14.PaO2_delta_lower_mmHg})))`
- **完整目标F**：`(((逐点全部满足((POST.ambientO2 ＝ 0.21{V2E-14.ambientO2_target})) 且 逐点全部满足((POST.ambientCO ＝ 0{V2E-14.ambientCO_target}))) 且 ((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-14.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-14.PaO2_delta_lower_mmHg}))) 且 (((均值((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2))) ≥ 0.1{V2E-14.SpO2_min_pp}) 且 (均值((W.PaO2 − B.PaO2)) > 0{V2E-14.PaO2_delta_lower_mmHg})) 且 逐点全部满足(((100{unit.fraction_to_percent} × (W.SpO2 − B.SpO2)) ≥ 0.5{V2E-14.SpO2_full_pp})) 且 逐点全部满足(((W.PaO2 − B.PaO2) > 0{V2E-14.PaO2_delta_lower_mmHg}))) 且 末窗目标低氧事件不活跃{target_events_inactive_W})`

</details>

## 四、容易混淆的判定逻辑

1. **01/04没有P**：本版只判断固定单源是否完全停止持续出血；最低目标与完整目标相同，没有定义部分止血阈值。不能自行加P。
2. **02/03/05/06用zero**：目的是评价已停源后额外补液或输血的增量。CO增量分母是共同治疗前CO；分子是Treatment−zero，不能改成Treatment−自身基线，也不能把整条联合链相对未治疗的改善全部归因于支持治疗。
3. **07恶化更少可能是P**：相对Control占优可以满足最低目标，即使患者自身仍恶化；E另外要求自身氧合持续改善与MAP全窗不降。安全风险照常报告。
4. **08比较健康区间距离**：指标越高或越低都未必更好，规则关注向匹配健康区间靠近的比例；20%/50%缩短并不要求完全回到区间。基线距离为0时改为全窗保持区间，不能伪造分母。健康参考仅限匹配Pulse研究配置，不是通用临床正常范围。
5. **09的两种模式**：SpO₂在94%～98%且PaO₂在75～100 mmHg的基线进入维持模式，两者都不能下降；至少一项低于下界且两项不超过上界进入改善模式，需达到自身氧合改善阈值。其余组合不可评价。两种模式都必须满足积血、潮气量和机制条件；E1是机制证据，不是E等级。
6. **10同时看PaCO₂和VT/PBW**：前者评价CO₂排出，后者评价按患者预测体重归一化的通气量。基线正常时要求维持，不要求越低越好；仅满足其中之一不足以满足目标。
7. **12容量与Na分开**：CO、血容量、总体液改善不证明电解质已纠正；Na轨迹及高钠异常仍是独立安全证据。健康体液端点必须同患者，kg不能直接当mL。
8. **13的g/dL与下降百分比**：原变量是COHb质量浓度，5%/10%是该浓度相对自身治疗前的下降比例，不是COHb饱和百分比，也不是下降5/10个百分点。CO环境清零不代表体内COHb清零。
9. **14还检查低氧事件**：血氧数值改善与原生目标低氧事件解除是不同证据。E要求末窗目标事件不活跃；早期事件仍须报告，不能只保留末窗“好看”的结果。
10. **安全与疗效分开**：E/P/I反映限定局部研究目标；独立安全状态为VETO、UNRESOLVED或NO_DEFINED_VETO_OBSERVED，后者也不是临床安全认证。严重事件、完整POST趋势和缺测不能被末窗均值或E遮住；原基线异常与新发恶化分别记录，医学审批状态不因本汇总变为已批准。

**精度提醒**：SpO₂增加0.1个百分点，例如从90.0%到90.1%，不是相对增长0.1%；“全窗满足”不能改成“平均满足”。表内所有“且”“同时”均为AND，只有明确模式分支和源AST的“或”才能选择。

## 五、版本与验证状态

| 项目 | 状态 |
| -- | -- |
| 规则版本 | Treatment Effect Rules V1.0 — Research Ruleset |
| 规则数量 | 14条：12条E/P/I；2条E/I（01、04，P不适用） |
| 适用范围 | Pulse 4.3.2固定研究Profile；不扩展伤情、Severity、动作或人群范围 |
| 研究规则状态 | `RESEARCH_RULESET_V1_LOCKED` |
| 最终离线测试 | 382项通过，0失败、0错误、0跳过；包括历史回放、Mock与工程门控测试 |
| 独立验证状态 | `INDEPENDENT_NATIVE_VALIDATION_PENDING` |
| 新独立Pulse实验 | H00 1支＋32支响应（18组比较）尚未完成；本次未运行任何Pulse实验 |
| 临床与启用边界 | 不宣称临床有效性已验证；正式评分、生产权限及真实运行许可未因本汇总启用 |
| 规则JSON SHA-256 | `6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f` |

**规则设计已经定稿，独立实验验证尚未完成。** 本文是锁定规则的人读说明，不是新候选版。唯一规则内容来源：`../final_rule_calibration_v1/FINAL_RULE_TABLE.json`；锁定的字节相同副本：`../treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json`。发布状态以该目录RULE_VERSION_MANIFEST.json为准；源JSON保留的PENDING字段属于来源中的医学/正式启用状态，不能解释为本次研究版未定稿，也不能擅自改成医学已批准。
