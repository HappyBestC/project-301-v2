# V2独立科研正式基线

2026-10-19（Asia/Shanghai）。本文件是个人科研工程的唯一正式模型入口，不是横向交付版本。最新净化验收见RESEARCH_CLEANUP_REPORT.md；此前迁移PASS仅为历史记录。本轮不新增医学决策、资源参数、Agent或M3功能。

## 正式采用的范围

| 内容 | 版本、来源与约束 |
|---|---|
| 十类单伤 | `301.v2.restricted.engineering.baseline.1`；`research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json`，执行注册表`src/core301/runtime/v2/restricted_registry.py`。受限准入`301.v2.restricted.acceptance.1` |
| 五类固定复合伤 | `301.v2_1.restricted.engineering.baseline.1`；`config/v2_1_battle_composite_patterns.yaml`、FIVE_COMPOSITE_CONFIGURATIONS.json。配置`301.v2_1.composite.runtime.1`，准入`301.v2_1.admission.2`、风险`301.v2_1.risk_gate.2`；胸部采用`301.v2_1.thoracic.aligned_onsets.2`，其余`301.v2_1.composite.candidate.1`；只允许固定AB |
| Pulse | 4.3.2、0.02秒步长，原生库SHA `f7eeb22ccef5392b2c0e2698037bc0aa47b0bf595f959c4c8dbc94f5d48023cf`。不扩展患者、部位、严重度、剂量、环境或组合范围 |
| 当前观测 | 旧V1 projector、V2受限`301.v2.restricted.observation.1`及专用血胸/暴露路径仍实际使用 |
| 新观测档案 | `301.observation.v2.engineering.baseline.1`；冻结标识`301.patient_observation.frozen.v2`、`301.evaluation_observation.frozen.v2`。实现仍带candidate.v2.1字面量；档案`user_acceptance=PENDING`、`runtime_activated=false`。已迁移schema/字段和原实现，不宣称全Runtime已切换十五指标 |

十类范围以配置为准：external_hemorrhage、abdominal_internal_hemorrhage、open_pneumothorax、closed_tension_pneumothorax、hemothorax、respiratory_muscle_impairment、impaired_alveolar_exchange、dehydration、carbon_monoxide_exposure、environmental_hypoxia。五复合为胸部穿透伤、胸腹钝伤、爆炸出血呼吸伤、火灾CO/肺泡伤、受困低氧脱水；精确英文scope及固定序列见配置，不以中文简称推导新组合。

## 十二动作与参数冻结

`control_external_bleeding`、`fluid_resuscitation`、`transfusion`、`control_internal_bleeding`、`occlusive_dressing`、`needle_decompression`、`control_hemothorax_bleeding`、`chest_tube`、`intubation`、`mechanical_ventilation`、`supplemental_oxygen`、`remove_from_exposure`。

定义/前置依赖沿用`dispatch/complete_contracts.py`、`runtime/v2_1/resources.py`、`pulse/v2/protocol_book.py`、专用血胸/暴露适配器和原固定配置。`inhaled_albuterol`仍保留但未开放；其旧审计代码和负向测试不是准入许可。三种控源是改变伤情源的研究代理，不是真实外科手术；环境移除是修改环境，不表示已完成患者转运。

## 疗效规则的唯一来源

正式锁定为V2E-01—14，`Treatment Effect Rules V1.0 — Research Ruleset`，`RESEARCH_RULESET_V1_LOCKED`。

权威目录：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/`。文件名中的candidate不否定其内部正式锁定版本；旧`.../treatment_effect_rules_v1.0_research_freeze/`里的R01—R14是另一套规则，本轮不把它当作正式规则迁入。

- 规则文件SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。
- 参数canonical SHA：`ed3ed8ae24f4da9f887202318c372f60a39ff95d3b9ffecf91b7870819c090f7`。
- 定义canonical SHA：`634a7a9abd54dac6643a9dd61303b80160fbc1bd7236fb691d802ef1f1aa3de2`。
- V2E-01/04为二分类定义，其余十二条有P定义；阈值和公式字节不变。

评价依赖链原样保留：`male_independent_validation_final_preparation_v1/adapter.py` → `common.py`/`reference.py` → `final_rule_calibration_v1/calibrate.py` → `research_candidate_v2_2_prelock/offline.py` → `final_lock_and_validation_v0.1/candidate_eval.py`，参考提取沿用`healthy_analysis.py`。这些旧名称是实际算法依赖，不是第二套新规则。`adapter.evaluate`接收证据manifest，`compute`调用原AST；仍保留formal_grade=null、formal_scoring_enabled=false及证据拒绝语义。主Runtime旧`core301.evaluation`评价器不等于这十四条新规则闭环。全历史load_case/批量replay工具及数据未作为新工程入口提供；不得运行旧脚本以重新校准或重建冻结文件。

锁定manifest记载的“独立验证待完成”为锁定时历史状态。后续各pulse_validation*/PULSE_VALIDATION_RESULTS.md已有真实Pulse研究证据，本轮保留报告索引，没有重新仿真或改写报告。M1索引记载后续首轮14条AST输出为10 E、3 P、1 I；不能称14条疗效均通过，亦不能将缺测导致的I解释为治疗无效。历史不同患者/协议证据不能混为本轮验收。

## Agent与共享调度

| 模块 | 当前事实 |
|---|---|
| Treatment Agent | 真实LLMTreatmentProvider、医学Prompt及V1八动作输出原样保留；ManualProvider只返回给定计划 |
| Resource Scheduling Agent | 原Fixed/LLM Provider、五字段DispatchProposal、ETA、TaskEvent与执行校验保留；本轮只Mock与HTTP Mock，无真实API调用 |
| M1 | 医疗资源/能力映射与未决需求保留；研究令牌、数量不能当临床规范 |
| M2-A | SharedResourceManager，`301.resource.m2a.1`；共享版本、幂等、整组预留、使用/消耗/释放和冲突。单进程共享实例，不支持持久化/跨进程恢复 |
| M2-B | SharedDispatchCoordinator，`301.dispatch.shared.1`；复用旧队伍/车/机构容量生命周期；不是第二份权威医疗库存 |
| M2-C | `301.treatment.complete.1`、`301.dispatch.complete.1`；十二动作、完整scope/串行依赖、无损兼容桥接、统一调度和原管理器原子预留 |

## 验证层次与未实现项

静态合同与Mock调度：已实现并在新工程回归。研究资源原子预留：真实管理器已验证，使用显式研究fixture。真实Pulse历史验证：限原冻结患者/部位/严重度/协议及报告层次；本轮仅初态加载与五基础指标读取，不是新方案疗效验证。

真实救助LLM生成十二动作完整计划：未实现。双Agent资源反馈/重新规划：未实现。CompletePlan到Pulse执行及十四规则闭环：未集成。Unity实际联调：未验证。临床资源规格、资质、时长和血液兼容：未确认，clinical_design仍INDETERMINATE。

## 冻结与开发边界

冻结伤情/复合配置、动作语义、医学Prompt、规则阈值/参数和原证据SHA保持不变。后续若修改应新建版本并另行验证，不能回写历史manifest掩盖变化。可继续开发新的M3版本接口、测试和文档，但本轮止于科研清理。

当前运行完整性：`research_baseline/CURRENT_RESEARCH_FILES.json`；清理改动与源SHA见`research_baseline/cleanup/`。旧迁移记录已隔离至`research_baseline/history/migration/`，不作为当前目录清单。两份V1 YAML字节未变，移至config/compatibility/v1；paths.py仅做路径重定向，医学Prompt、正式配置和算法不变。重要SHA如下：

| 文件 | SHA-256 |
|---|---|
| `research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json` | `a8bc0a321a2c3ca0122896c472ac3c8b376a38017ea5ccc752cdb8b7836c652e` |
| `config/v2_1_battle_composite_patterns.yaml` | `cd339d0748b8016d7aad52580562d462807ea56504dd85c1f0ce4703b1d34bf1` |
| `research_artifacts/v2_1_restricted_engineering_baseline_v1.0/FIVE_COMPOSITE_CONFIGURATIONS.json` | `4d9e2d6bf5288ce57ba9f09909f21de389b33e92144c8b2bffa747880a9678b0` |
| `research_artifacts/observation_v2_contract_freeze_v1.0/VERSIONS.json` | `7101351c2cbb6f77c45a0bd110592fbf9c754f3a38dcf7ccd5008c79c35ec228` |
| `research_artifacts/treatment_effect_rules_v2_candidate_v0.1/treatment_effect_rules_v1_final/FINAL_RULE_TABLE_V1.0.json` | `6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f` |
| `src/core301/agent/prompts/treatment_decision.md` | `b0cfb8a132af1cc8e0466a53a582ecacaaeff2c5ef79780f8dbf12d240fc7472` |
| `src/core301/dispatch/shared_resources/manager.py` | `23cf9cf480526c990fca93bad36746203d4012f6f25659f02cdd83bbd308d48c` |
| `src/core301/dispatch/shared_integration.py` | `4c277e38be11d7d61351fea3b1b89b85f6f062627d7c3cdbbe5eba437a2547a4` |
| `src/core301/dispatch/complete_contracts.py` | `863122ea533dd4efc8549c1221691656b016762be75fa8a7e4f2a4364a7395ad` |

## 科研与兼容隔离

根目录V1冻结文档已移除。config/compatibility/v1仅服务当前真实Treatment LLM旧合同及兼容测试；它的十模板/六模式不取代上述正式V2十类受限配置/五类复合。已验证男性患者的工程StandardMale与后续Soldier研究证据按各自manifest适用，不扩展范围。科研路线聚焦MAS，Unity横向联调不作为本工程后续交付目标。
