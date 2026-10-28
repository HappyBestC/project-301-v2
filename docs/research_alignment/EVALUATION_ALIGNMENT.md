# 十四条锁定疗效评价规则核查

审查日期：2026-10-19。仅依据当前科研工程的实际文件、源码和已迁入验证记录；本轮未运行新的 Pulse 治疗实验或真实 LLM。MATCHED 表示所指层次一致，PARTIAL 表示定义一致但链路不完整，MISMATCH 表示具体冲突，UNVERIFIED 表示证据不足。历史报告中的 PASS 不自动转为本轮实测结论。

## 内容一致性与 SHA

实际读取用户材料正文、展开表达式，并逐项核对 JSON 的 prerequisites、eligibility、minimum、complete、grade_contract、grade_predicates、fixed_scope、evaluation_window 与 parameter_registry。用户上传的规则 Markdown 与归档 `treatment_effect_rules_v1_summary_v1` 同名文件**逐字节一致**。

来源：[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/FINAL_RULE_TABLE.json](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/FINAL_RULE_TABLE.json)；字节相同锁定副本：[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json)；状态依据：[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/RULE_VERSION_MANIFEST.json](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/RULE_VERSION_MANIFEST.json)，状态 `RESEARCH_RULESET_V1_LOCKED`。

|核验项|本轮实际 SHA256|结果|
|---|---|---|
|源 JSON 与锁定副本文件字节|`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`|MATCHED，两个文件相同|
|parameter_registry canonical|`ed3ed8ae24f4da9f887202318c372f60a39ff95d3b9ffecf91b7870819c090f7`|MATCHED|
|definitions canonical|`634a7a9abd54dac6643a9dd61303b80160fbc1bd7236fb691d802ef1f1aa3de2`|MATCHED|

canonical 实际采用 UTF-8、`json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`；definitions对象为 `{rule_id: rule.definitions}`，不是整个rules数组。没有修改任何参数/公式，也没有根据材料反写冻结配置。

## 通用判定与逐规则核查

B为实际治疗前单点；W为终点前末60秒；C为对应合法对照的同时间网格；H为胸腔高频窗口；POST为治疗后全过程。公共采样通常1s，07/08机制高频.02s；常见末窗含两端为61点。既有浮点时刻按原代码时间政策处理，不能舍弃不利端点。

在可评价前提下 E=F，P=M且非F，I=非M；01/04不适用P。缺数据、单位/授权/时间/范围/对照/必要机制或参考不合法应 NOT_EVALUABLE，不能统一降I。安全输出独立为VETO/UNRESOLVED/NO_DEFINED_VETO_OBSERVED，不由疗效E抵消。正式评分 `formal_scoring_enabled=false`；研究等级并非临床治愈。

下表按材料/锁定定义对照为 MATCHED，当前完整救助 Runtime 接通为 PARTIAL。历史结果仅引述当前工程保留的既有真实 Pulse 报告，不是本轮复算或新实验。

|规则|固定范围与决策/终点|动作|主要指标|最低目标M|完整目标F|必要对照/机制|状态与历史结果|
|---|---|---|---|---|---|---|---|
|V2E-01|RightLeg 外出血 .4；180→480s|`control_external_bleeding`|出血率、累计失血|单源身份；W每点出血率=0且累计失血相对W首点变化=0|M=F；不设P|匹配未治疗对照；同源控源证据|MATCHED / PARTIAL；历史E|
|V2E-02|RightLeg 外出血 .4；180→480s|`control_external_bleeding → fluid_resuscitation`|CO|g=100×(W.CO−Czero.CO)/B.CO；mean(g)≥2%|M且all(g≥6%)|合法zero；先控源；Saline/Blood互斥|MATCHED / PARTIAL；历史E|
|V2E-03|RightLeg 外出血 .4；180→480s|`control_external_bleeding → transfusion`|CO|同02，mean(g)≥2%|M且all(g≥6%)|合法zero；先控源；支持互斥|MATCHED / PARTIAL；历史E|
|V2E-04|Spleen 内出血 .4；180→480s|`control_internal_bleeding`|出血率、累计失血、腹腔积血|同01且W每点腹腔积血相对W首点变化=0|M=F；不设P|匹配未治疗；同源与腹腔机制|MATCHED / PARTIAL；历史E|
|V2E-05|Spleen 内出血 .4；180→480s|`control_internal_bleeding → fluid_resuscitation`|CO|同02定义g，mean(g)≥2%|M且all(g≥5.5%)|合法zero；停源与互斥|MATCHED / PARTIAL；历史E|
|V2E-06|Spleen 内出血 .4；180→480s|`control_internal_bleeding → transfusion`|CO|同02定义g，mean(g)≥2%|M且all(g≥5.5%)|合法zero；停源与互斥|MATCHED / PARTIAL；历史E|
|V2E-07|开放气胸 Left .6；180→480s|`occlusive_dressing`|SpO₂、PaO₂、MAP及通路|终点胸封通路阻断；平均相对未治疗SpO₂优势≥.1pp、PaO₂优势>0|M＋自身全窗SpO₂增益≥.5pp、PaO₂增益>0、MAP变化≥0|匹配未治疗；.02s通路证据；accepted不是阻断证明|MATCHED / PARTIAL；历史P|
|V2E-08|闭合张力气胸 Left .6；180→480s|`needle_decompression`|SpO₂、PaO₂、MAP；胸膜压力/容积|针路通畅；自身氧合平均增益≥.1pp / >0；压力及容积到健康区间距离平均各缩短≥20%|M＋自身氧合全窗≥.5pp / >0；两距离全窗各缩短≥50%；MAP全窗不降|匹配健康区间；高频H；初始距离0改为全窗在区间，不能除零|MATCHED / PARTIAL；历史P|
|V2E-09|血胸 Left .8；660→960s|`control_hemothorax_bleeding → chest_tube`|胸腔积血、VT、SpO₂、PaO₂|E1_complete；平均积血减≥20%；VT全窗≥90%基线；合法氧合维持/改善模式|M＋平均积血减≥90%；all(abs(残余)≤1mL)；原生自动停管；相应完整氧合目标|E1可用时点、源/管活动、流率、负残值、自动停止日志|MATCHED / PARTIAL；历史I（E1缺测解释限制）|
|V2E-10|呼吸肌受损 .4；180→480s|`intubation → mechanical_ventilation`|PaCO₂、VT/PBW|通气设备支持；PaCO₂异常到[35,45]距离平均减≥20%，正常则≥80%点在区间；mean(VT/PBW)∈[4,8]|M＋异常距离全窗减≥50%或正常100%在区间；all(VT/PBW∈[4,8])|PBW来自真实性别/身高；设备生效和匹配未治疗|MATCHED / PARTIAL；历史E|
|V2E-11|肺泡交换受损 .2/.4/.6分别；180→480s|`supplemental_oxygen`|SpO₂、PaO₂、FiO₂|设备支持、FiO₂有限；自身氧合平均增益≥.1pp / >0|M＋自身全窗SpO₂增益≥.5pp、PaO₂增益>0|固定鼻导管；未治疗对照；历史首轮.4不代表三个档位全部独立验证|MATCHED / PARTIAL；历史E（首轮.4）|
|V2E-12|脱水 .2/.4/.6分别；180→480s|`fluid_resuscitation`|CO、MAP、总体液fluid、血量BV；Na安全项|自身CO平均增≥2%；MAP平均不降；fluid/BV平均各增≥50mL；平均剩余液缺口小于初始缺口|M＋CO全窗增≥5%；fluid/BV全窗各增≥100mL；剩余缺口全窗≤初始10%；总体液全窗≤H1|H0健康0秒、H1健康300秒上界；D0=H0−B.fluid>0；Na不作疗效加分|MATCHED / PARTIAL；历史P（首轮.4）|
|V2E-13|CO .005 / O₂ .21；960→1860s|`remove_from_exposure`|COHb质量浓度、环境CO/O₂|POST全程CO=0/O₂=.21；COHb相对自身基线平均下降≥5%|M＋全窗下降≥10%|匹配未治疗；实际环境与浓度轨迹；不能用CO饱和度替代|MATCHED / PARTIAL；历史E|
|V2E-14|O₂ .12 / CO0；360→660s|`remove_from_exposure`|SpO₂、PaO₂、环境O₂/CO、事件|POST全程O₂=.21/CO0；自身氧合平均增益≥.1pp / >0|M＋全窗自身SpO₂增益≥.5pp、PaO₂增益>0；W目标缺氧事件不活动|匹配未治疗；完整事件及实际气体；非设备FiO₂替代|MATCHED / PARTIAL；历史E|

09氧合模式：基线SpO₂∈[.94,.98]且PaO₂∈[75,100]时，M/F均要求两者全窗不低于基线；至少一项偏低且两项均不超过上界时，M要求自身平均SpO₂增≥.1pp、PaO₂>0，F另要求全窗≥.5pp及>0。高于上界等未定义模式不可强行选择，须 NOT_EVALUABLE。胸腔血量不是出血率，微小负残值不能裁零。01/04要求末窗平台，不要求已失血量或腹腔积血回零。

08使用原生绝对胸膜压力cmH₂O与胸膜容积mL，对匹配健康区间计算距离；不能换成表压或单个终点。10 PBW按性别/身高算，不把历史Soldier恰好75.3kg写成通用常数。11/12多严重度必须分别核验，不因有一个.4首轮结果就称全部档位通过。

## 实际 AST 和调用入口

1. [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/calibrate.py](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/final_rule_calibration_v1/calibrate.py): `config/eval_node/validate/predicate/evaluate_case`。读取固定JSON，递归计算原AST，委托 `research_candidate_v2_2_prelock/offline.py` 和其既有底层运算；并非仅有人读规则表。
2. [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/common.py](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/common.py): 固定 RULE_SHA；[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/adapter.py](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/male_independent_validation_final_preparation_v1/adapter.py): `manifest_plan/assemble/compute/evaluate`。读取 pinned manifest/观察/动作/事件/参考，核对单位、时序、患者、配对、源SHA。CLI接收 manifest，有实际研究调用入口；**不是可直接接收当前 EvaluationObservationV2 的API**。
3. `compute` 返回 minimum/complete 子条件及安全、`formal_grade=None`；成功状态 `COMPUTABLE_SUBCONDITIONS_ONLY`。研究 grade_predicates 已定义，历史驱动曾输出研究 E/P/I；不能因此说当前主服务开启正式评分。
4. [src/core301/evaluation](../../src/core301/evaluation) 是已有另一套评价模块，[tests/test_evaluation.py](../../tests/test_evaluation.py) 和 `test_evaluation_integration.py` 不能当作十四锁定规则全链路测试。当前 `src/core301/runtime` / `agent` 没有调用上述锁定适配器的完整链路，也没有将其结果用于后续重规划。
5. 当前工程未迁入独立 native driver 的完整大型 campaigns 原始数据。适配器源码存在不等于在本工程有可完整复现的真实 manifest 数据集。使用缺失路径的CLI也不会自动得到有效研究评价。

## 历史证据、冲突和限制

### D1：状态快照与后续实验进展

**MISMATCH（把历史快照当当前状态时）**：用户规则材料末尾及发布manifest记载独立实验待完成，manifest原计划完成0。这是锁定时事实，不能回写原档案。后续 [research_artifacts/treatment_effect_rules_v2_candidate_v0.1/pulse_validation_09_v1/PULSE_VALIDATION_RESULTS.md](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/pulse_validation_09_v1/PULSE_VALIDATION_RESULTS.md) 汇总十四规则已有首轮原AST输出：01/02/03/04/05/06/10/11/13/14为E，07/08/12为P，09为I。材料的规则定义仍 MATCHED；“全部32响应已完整验收”仍无此结论。

分组证据：`pulse_validation_14_02_03_v1`、`pulse_validation_02_03_v1`、`pulse_validation_04_05_06_v1`、`pulse_validation_07_08_09_v2`、`pulse_validation_08_09_v1`、`pulse_validation_09_v1`、`pulse_validation_10_v1`、`pulse_validation_11_13_v1`、`pulse_validation_12_recovery_v1` 下各 `PULSE_VALIDATION_RESULTS.md`。这些路径均位于本报告上方R目录。失败/中止的早期批次不能与后续成功重复累计。

### D2：05/06报告公式文字冲突

**MISMATCH**：[research_artifacts/treatment_effect_rules_v2_candidate_v0.1/pulse_validation_04_05_06_v1/PULSE_VALIDATION_RESULTS.md](../../research_artifacts/treatment_effect_rules_v2_candidate_v0.1/pulse_validation_04_05_06_v1/PULSE_VALIDATION_RESULTS.md) 在主表后写“(Treatment CO−zero CO)/zero CO×100%”；材料第395行及锁定02/03/05/06 AST均为 **100×(W.CO−C.CO)/B.CO**。分母为共同治疗前CO，不是每个末窗zero采样。该报告其他部分声明使用原AST，故目前可确认的是解释文本冲突；没有本地原始轨迹，不能扩大判断为计算结果错误。后续应补一份可追溯勘误/复算说明，本轮不改原报告或规则。

### D3：09缺测与I的解释缺口

**PARTIAL**：09报告明确660.02s置管瞬间 `tube_action_active=true` 但流率为null，E1返回false，再进入M/F得到I。已有记录称后续积血减少、引流及自动停止成立，故该I不能证明生理治疗无效。通常缺必要证据应 NOT_EVALUABLE 的合同原则，与这里“缺测折成机制false”的行为存在语义缺口；必须保留原I及原始缺测，不补零、不填30、不擅自改等级。材料本身已提示该类证据边界，待后续专门确认适配层如何分类。

### D4：患者与复合范围

**PARTIAL**：受限Runtime用StandardMale，独立规则实验用固定Soldier及原manifest。需要显式患者/参考绑定桥接，不能直接迁用健康参考。十四规则为固定单项治疗局部目标；五复合AB的工程验收不等于十四规则自动适用于复合整体效果。组合多源与不同时序可能不满足single_source、fixed_scope或配对条件，应拒评而非复用单伤等级。

### 本轮证据上限

上述历史原生结果有已保留的报告支持；未在本轮重新运行/复算。原始campaign缺失时，对原始文件SHA、轨迹数值和真实执行完整性的独立本地重验标记 **UNVERIFIED**。三项规则内容SHA则是本轮实际重算并通过，两者分开。

## 锁定 M/F 参数引用核对表

下表直接从当前 JSON definitions 提取引用并解析 parameter_registry；保持原值。健康区间是该规则快照的匹配参考，不是普适临床正常值；独立适配器允许按原有参考绑定政策产生effective context，须与基础参数SHA分别记录。

|规则|M/F及前置定义引用的锁定参数值|
|---|---|
|V2E-01|`V2E-01.cumulative_change_target`=0；`V2E-01.source_rate_target`=0|
|V2E-02|`V2E-02.co_full_pct`=6；`V2E-02.co_min_pct`=2；`unit.fraction_to_percent`=100|
|V2E-03|`V2E-03.co_full_pct`=6；`V2E-03.co_min_pct`=2；`unit.fraction_to_percent`=100|
|V2E-04|`V2E-04.abdominal_change_target`=0；`V2E-04.cumulative_change_target`=0；`V2E-04.source_rate_target`=0|
|V2E-05|`V2E-05.co_full_pct`=5.5；`V2E-05.co_min_pct`=2；`unit.fraction_to_percent`=100|
|V2E-06|`V2E-06.co_full_pct`=5.5；`V2E-06.co_min_pct`=2；`unit.fraction_to_percent`=100|
|V2E-07|`V2E-07.PaO2_delta_lower_mmHg`=0；`V2E-07.SpO2_full_pp`=0.5；`V2E-07.SpO2_min_pp`=0.1；`V2E-07.complete_MAP_change_mmHg`=0；`V2E-07.relative_PaO2_min_mmHg`=0；`V2E-07.relative_SpO2_min_pp`=0.1；`unit.fraction_to_percent`=100|
|V2E-08|`V2E-08.PaO2_delta_lower_mmHg`=0；`V2E-08.SpO2_full_pp`=0.5；`V2E-08.SpO2_min_pp`=0.1；`V2E-08.complete_MAP_change_mmHg`=0；`V2E-08.mechanism_full_distance_reduction_pct`=50；`V2E-08.mechanism_min_distance_reduction_pct`=20；`constant.zero`=0；`reference.pressure_final_range`=[1024.4718877946036, 1029.796423698125]；`reference.volume_final_range`=[948.3006123152339, 1450.6802880244936]；`unit.fraction_to_percent`=100|
|V2E-09|`V2E-09.PaO2_delta_lower_mmHg`=0；`V2E-09.SpO2_full_pp`=0.5；`V2E-09.SpO2_min_pp`=0.1；`V2E-09.maintenance_PaO2_drop_budget`=0；`V2E-09.maintenance_SpO2_drop_budget`=0；`V2E-09.maintenance_baseline_PaO2_range`=[75, 100]；`V2E-09.maintenance_baseline_SpO2_range`=[0.94, 0.98]；`V2E-09.residual_abs_max_mL`=1；`V2E-09.tidal_volume_floor_fraction_B`=0.9；`V2E-09.volume_reduction_full_pct`=90；`V2E-09.volume_reduction_min_pct`=20；`constant.minus_one`=-1；`index.lower`=0；`index.upper`=1；`unit.fraction_to_percent`=100|
|V2E-10|`V2E-10.PaCO2_target_mmHg`=[35, 45]；`V2E-10.VT_PBW_mL_kg`=[4, 8]；`V2E-10.distance_reduction_full_pct`=50；`V2E-10.distance_reduction_min_pct`=20；`V2E-10.maintenance_fraction_full`=1；`V2E-10.maintenance_fraction_min`=0.8；`constant.zero`=0；`unit.fraction_to_percent`=100|
|V2E-11|`V2E-11.PaO2_delta_lower_mmHg`=0；`V2E-11.SpO2_full_pp`=0.5；`V2E-11.SpO2_min_pp`=0.1；`unit.fraction_to_percent`=100|
|V2E-12|`V2E-12.MAP_min_mean_change_mmHg`=0；`V2E-12.blood_volume_full_increase_mL`=100；`V2E-12.blood_volume_min_increase_mL`=50；`V2E-12.co_full_self_pct`=5；`V2E-12.co_min_self_pct`=2；`V2E-12.fluid_full_increase_mL`=100；`V2E-12.fluid_min_increase_mL`=50；`V2E-12.residual_fraction_of_initial_deficit`=0.1；`constant.zero`=0；`unit.fraction_to_percent`=100|
|V2E-13|`V2E-13.COHb_full_drop_pct`=10；`V2E-13.COHb_min_drop_pct`=5；`V2E-13.ambientCO_target`=0；`V2E-13.ambientO2_target`=0.21；`unit.fraction_to_percent`=100|
|V2E-14|`V2E-14.PaO2_delta_lower_mmHg`=0；`V2E-14.SpO2_full_pp`=0.5；`V2E-14.SpO2_min_pp`=0.1；`V2E-14.ambientCO_target`=0；`V2E-14.ambientO2_target`=0.21；`unit.fraction_to_percent`=100|
