# 初始病例数据验证报告

范围：真实 Pulse 初始数据、后台证据、基础观察投影和候选动作模板。未运行治疗、调度 Agent 或 RAG。

## 版本与证据

Pulse 4.3.2；实际接口为 PyPulse.Engine(human_adult_whole_body)，复用 ResearchPulseSession/Session，原生步长 0.02s；项目包 0.1.0。服务器无 Git 仓库，不能提供 commit；129 个 Python 源文件的整体哈希为 `d3ea239212ea9fd3eb4565391aeb4f343b9d511954fa4e5b033c2a98ca0be43a`，逐文件及引擎二进制哈希见 source_audit.json。
当前代码与归档中全部可对应 Python 文件逐一哈希一致。15 项目录与冻结 metric_catalog 的 agent 部分完全一致。所有保护目录及项目源码校验通过。

## 采样与时间

StandardMale；基本状态和患者文件均通过原工程固定 SHA 检查。急性伤情先健康推进 60s，施伤后 120s 采样（Pulse t=180s）；血胸施伤后 600s（t=660s）；CO 暴露 900s（t=960s）；低氧暴露 300s（t=360s）。CO/O₂ 分别 0.005/0.21 和 0/0.12；CO₂=0.0004，N₂ 补足，四组分合计 1。采样时暴露持续。完整环境状态随证据保留。
脱水 Severity 0.4 通过 PatientInitializer 配置，Pulse initialize_engine 原生稳定化，随后按现有 CaseRuntime 推进 60+120s。稳定化进度与是否成功见 P08/execution.log；伤后时长不伪造，保存 null。
采用既有研究准备时长，并非新增医学验证；未用默认 5min。配置在运行前保存并锁定 SHA。1Hz 原始采样，0.02s 检查原生事件；保留原始浮点仿真时间。调度时间只由 evidence/timing 的 offset 映射。

## 逐例结果

| 病例 | 伤情 | 状态 | 来源与采样 |
|---|---|---|---|
| P01 | external_hemorrhage | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P02 | abdominal_internal_hemorrhage | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P03 | respiratory_muscle_impairment | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P04 | carbon_monoxide_exposure | 生成成功，条件投影待授权 | 独立运行；t=960.00s |
| P05 | closed_tension_pneumothorax | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P06 | abdominal_internal_hemorrhage | 生成成功，条件投影待授权 | 复用 P02；t=180.00s |
| P07 | hemothorax | 生成成功，条件投影待授权 | 独立运行；t=660.00s |
| P08 | dehydration | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P09 | external_hemorrhage | 生成成功，条件投影待授权 | 复用 P01；t=180.00s |
| P10 | open_pneumothorax | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P11 | closed_tension_pneumothorax | 生成成功，条件投影待授权 | 复用 P05；t=180.00s |
| P12 | impaired_alveolar_exchange | 生成成功，条件投影待授权 | 独立运行；t=180.00s |
| P13 | respiratory_muscle_impairment | 生成成功，条件投影待授权 | 复用 P03；t=180.00s |
| P14 | environmental_hypoxia | 生成成功，条件投影待授权 | 独立运行；t=360.00s |
| P15 | external_hemorrhage | 生成成功，条件投影待授权 | 复用 P01；t=180.00s |
| P16 | hemothorax | 生成成功，条件投影待授权 | 复用 P07；t=660.00s |

## 指标采集与投影

| 字段 | 单位 | 后台可用 | 发布人数 | 候选待授权人数 |
|---|---|---:|---:|---:|
| vitals.heart_rate | 1/min | 16/16 | 16 | 0 |
| vitals.respiration_rate | 1/min | 16/16 | 16 | 0 |
| vitals.pulse_oximetry | 1 | 16/16 | 16 | 0 |
| vitals.systolic_arterial_pressure | mmHg | 16/16 | 16 | 0 |
| vitals.mean_arterial_pressure | mmHg | 16/16 | 16 | 0 |
| circulation.cardiac_output | L/min | 16/16 | 0 | 6 |
| respiratory.tidal_volume | mL | 16/16 | 0 | 7 |
| respiratory.inspired_oxygen_fraction | 1 | 16/16 | 0 | 2 |
| laboratory.hemoglobin_concentration | g/dL | 16/16 | 0 | 8 |
| laboratory.lactate_concentration | mg/dL | 16/16 | 0 | 0 |
| laboratory.arterial_oxygen_pressure | mmHg | 16/16 | 0 | 8 |
| laboratory.arterial_carbon_dioxide_pressure | mmHg | 16/16 | 0 | 3 |
| laboratory.blood_ph | 1 | 16/16 | 0 | 3 |
| laboratory.aorta_carboxyhemoglobin_concentration | g/dL | 16/16 | 0 | 1 |
| laboratory.aorta_sodium_concentration | mEq/L | 16/16 | 0 | 1 |

基础观察全部通过现有 project(Access()) 及 PatientObservationV2 Python 语义校验。后台 Measurement 另逐项验证。非有限值不会进入标准 JSON；原始请求缺测与未授权分别记录。后者不将实测值改成 unavailable。
COHb 为 g/dL，乳酸为 mg/dL；脉氧直接来自 PulseOximetry。患者 FiO₂、环境氧气、未施加的设备氧气设置分开记录。

## 差异与保留边界

1. 简明文档说“十类正式受限验收”，旧 contracts/v2/injury.py 仍含支气管收缩及 ARDS，环境异常由独立 ExposureInput 定义；protocol_book 旧 phase1 将血胸列为保留，但 restricted_registry 已有独立受限路径。没有修改任何入口；本批复用原生研究 Session、InjuryAdapter、PatientInitializer 和环境适配器，只运行准备过程。
2. Observation 文档冻结标识绑定的源码仍用 candidate.v2.1，VERSIONS 明确 runtime_activated=false、production_enabled=false。正式检验授权未接通，因此只发布基础五项，条件白名单保存在 observation_visibility_config.json 待集成。未伪造宿主授权；未将已知伤情直接解锁为检查结果。
3. 环境受限治疗入口会恢复治疗前检查点；本批保留连续原始会话的初值。恢复仅作独立核验，未覆盖原始指标或将两个分支拼接。保存状态可加载/即时读取不代表未来连续轨迹相同。
4. 资源文件是草案，耗时、库存、治疗停止、交接及适用条件未完整验证。计划均为 template_only_not_executed，补液/输血等仍 eligibility_pending。引用原固定协议与资源表，不执行动作时长。
5. 正式 EvaluationObservation 历史适配主要面向冻结回放；本批保存 independent_raw_evidence_not_EvaluationObservation，不冒称已符合该契约。
6. 资源文档里部分引用仍指向作者电脑 /Users/cjq/...；本次使用服务器 my-docs 副本，不把不可访问的外部文献当作本次验证依据。

## 恢复、事件与失败

原生状态独立恢复检查数：10。即时读取差异详情见 verification.json/restore_results；没有验证继续推进后的轨迹等价。
病例失败数：0。原生日志警告/错误行数：0，完整条目保存在 verification.json。原生事件按时间保存，不从严重事件直接推定死亡；死亡类别只标记 IrreversibleState。本次未使用自定医学阈值。

## 文件和复现

patients_initial.json 是病例索引；patient_specs.json 为机制配置；patient_observations/ 只含基础观察；evaluation_evidence/ 与 raw/ 是后端证据，不能整包给 Agent；action_plan_templates.json 为候选方案。复用病例 raw/Pxx/reuse.json 明确指向原始来源，未声称独立重复。
执行 `bash dataset_v1/run.sh dataset_v1/run_002` 可在新目录重新生成并验证。拒绝覆盖既有目录。manifest.json 记录文件 SHA，不包含自身哈希。
