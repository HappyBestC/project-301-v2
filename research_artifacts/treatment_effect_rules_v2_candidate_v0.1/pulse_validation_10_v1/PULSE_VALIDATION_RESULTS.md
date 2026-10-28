# V2E-10 真实 Pulse 验证结果

日期：2026-10-17；Pulse 4.3.2；新campaign `fatigue_10_v1`。

严格采用原Manifest：Soldier、RespiratoryFatigue Severity=0.4，60秒起病，180秒依次Tracheal插管与MechanicalVentilatorPressureControl，480秒结束，末窗420–480秒。AssistedControl、FiO₂=0.21、吸气压力13 cmH₂O、PEEP=5 cmH₂O、RR=12/min、吸气时间1秒、Slope=0.1秒。Control无救助，Treatment恢复同一治疗前状态。

患者PBW由现有适配器动态计算：性别Male，身高71.0 in，PBW=(50+2.3×(身高英寸−60))=75.3 kg；未硬编码PBW。原生患者信息见DEVICE_EVIDENCE.json。

|指标|治疗前|Treatment末窗均值 [最小, 最大]|Control末窗均值 [最小, 最大]|
|---|---|---|---|
|PaCO2 (mmHg)|43.273182|40.394092 [40.338450, 40.468717]|43.380949 [43.360312, 43.404938]|
|pH (1)|7.382579|7.409802 [7.409073, 7.410349]|7.381594 [7.381375, 7.381782]|
|VT (mL)|335.697398|440.992700 [439.668505, 442.000206]|350.333570 [349.958861, 350.619118]|
|SpO2 (1)|0.965072|0.974247 [0.974010, 0.974418]|0.966830 [0.966646, 0.967002]|
|PaO2 (mmHg)|79.059222|91.069780 [90.954467, 91.184541]|84.785257 [84.640075, 84.939855]|
|FiO2 (1)|0.209851|0.209234 [0.209224, 0.209240]|0.209899 [0.209898, 0.209900]|

VT/PBW末窗均值5.856477 mL/kg，范围[5.838891, 5.869857]；均值在4–8内：True；全窗每点在4–8内：True。
PaCO₂治疗前到35–45 mmHg区间距离：0.000000 mmHg。末窗正常比例：100.000000%。距离缩短统计（基线区间内则不定义除法）：None。

|M|F|锁定V1.0 AST研究等级|独立安全状态|
|---|---|---|---|
|True|True|E|UNRESOLVED|

判定直接来自原AST，不手工指定等级；上述数值计算仅用于解释。基线正常使用维持模式：M≥80%正常、F=100%；基线异常使用距离改善模式：M平均≥20%、F全窗≥50%。两种模式均须同时满足相应VT/PBW条件。

## 原生执行和安全证据

- 动作accepted：[True, True]；实际时间：[180.00000000001828, 180.00000000001828]。
- 原AST设备支持事实：{'value': True, 'source': 'research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/fatigue_10_v1/fatigue_s0.4_Treatment/final_state.json', 'source_sha256': 'a40f1d984ea4bcb7b82bf2ffa01a70805f0d475a968807de970cb09faa61d330', 'observed_at_s': 479.9999999998534, 'available_at_s': 479.9999999998534, 'authorized': True}。
- 原生终态的插管、气道和机械通气设备字段与ActiveActions完整保存在DEVICE_EVIDENCE.json，并绑定原final_state.json的SHA；不只根据accepted判断设备生效。
- 原生事件名称：['StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale', 'Tachypnea']。严重事件：[]；必需安全缺测：[]。
- 安全状态原因：PROFILE_MEDICAL_OWNER_EVENT_POLICY_PENDING；所有原始事件与安全数值保留。E不代表呼吸肌恢复，也不代表临床安全或治愈。

## 数据位置与完整性

- `fatigue_s0.4_Control`：ARCHIVED；`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/fatigue_10_v1/fatigue_s0.4_Control/`；执行回执SHA `8b980c2a6317b39463bd74bb8ba1e495f8b1f634fbb3719d5c35ade329090a0f`。
- `fatigue_s0.4_Treatment`：ARCHIVED；`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/fatigue_10_v1/fatigue_s0.4_Treatment/`；执行回执SHA `8a5870c014402171dd0b7d648453d733cd8f8d130da24b025846c634c25d2eaf`。

- 1110份保护文件SHA不变。未修改代码、规则、AST、阈值、患者或Manifest。两支逐支核验原始数据、回执、日志及SHA，Treatment原AST离线复算与原生运行后的评价完全一致。
- 原始数据包括raw_requests.jsonl、raw_native_events.jsonl、capture、原生动作、初态/治疗前态/终态、pulse.log及SHA256.json。运行命令见RUN_COMMANDS.txt。没有自动重试或运行其他规则。

## 设备实际生效与剩余异常

- 原生终态 `Intubation=On`、`AirwayMode=MechanicalVentilator`、`MechanicalVentilator.Common.Settings.Connection=On`。呼吸机瞬时吸气流量0.540224 L/s，设备潮气量0.439868 L，实际气道压力12.945977 cmH₂O；存在真实流量、压力和周期输出，不只是accepted回执。设备设置PEEP=5、吸气压力=13 cmH₂O、O₂比例=0.21均保留。
- 原生患者初始化状态与输入的身高、性别及计算PBW一致。男性是Pulse protobuf默认枚举，JSON可省略Sex；不是将PBW写死。
- Control约158.38秒开始出现Tachypnea，持续至480秒。Treatment在180秒恢复时已带有该事件，并持续至终点，不能宣称呼吸急促已解除。辅助控制下终态呼吸频率约25.21/min；设置12/min不等于患者实际频率必须为12/min。
- 未出现既定严重否决事件、必需安全指标缺测或新的数值安全触发；未解决安全状态原样保留。压力控制终态的DriverFlow_L_Per_s及PreviousDriverFlow_L_Per_s原生NaN字符串完整保留，未填零；实际呼吸流量、VT及全部规则必需指标均有有限值。
- 两支真实原生实验成功，原AST研究等级为E，本轮无技术阻塞；已有真实研究评价覆盖从9条推进到10条。未运行其他规则、未重试。
