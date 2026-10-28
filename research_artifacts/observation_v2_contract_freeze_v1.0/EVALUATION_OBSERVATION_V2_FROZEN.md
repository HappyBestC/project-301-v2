# 冻结工程契约：301.evaluation_observation.frozen.v2

归档日期 2026-10-14；基线 301.observation.v2.engineering.baseline.1。工程归档完成，用户最终验收待确认，Runtime 未启用。

以下原文逐字保留 B1 后候选语义；其中候选版本、待审核字样属于来源记录，不将其静默改写为新的运行时 Literal。冻结标识由 VERSIONS.json 绑定该源码与 Schema 的 SHA；N1 已知例外要求必经 Python 语义校验和可信投影。

---

# EvaluationObservation v2 候选

`301.evaluation_observation.candidate.v2.1`，CANDIDATE / REVIEW_REQUIRED / NOT_ACTIVATED。与 Agent 契约独立；不会由 PatientObservation 序列化入口自动携带。

frames 中每帧只有一份已门控 PatientObservation，加上 ResearchAccess 明确授予的诊断 Measurement。events 是原生事件转换记录（观测时间、名称、激活/解除、原生持续时间）；actions 是原生提交回执的时间/阶段/状态，包含负面测试阶段，**accepted 不等于机制成立或疗效有效**。source_snapshots 仅在原生初态、治疗前、验收终点记载活动源名称/类型/部位；“不在活动列表”不被本模块判为控制成功。

| 内部字段 | 单位 | 原生来源 |
|---|---|---|
| `diagnostic.BloodVolume` | mL | Physiology / BloodVolume |
| `diagnostic.TotalHemorrhageRate` | mL/s | Physiology / TotalHemorrhageRate |
| `diagnostic.TotalHemorrhagedVolume` | mL | Physiology / TotalHemorrhagedVolume |
| `diagnostic.AbdominalCavityVolume` | mL | LiquidCompartment / AbdominalCavity / Volume |
| `aorta_co_saturation` | 1 | LiquidCompartment / Aorta / CarbonMonoxide / Saturation |
| `aorta_cohb_g_dL` | g/dL | LiquidCompartment / Aorta / Carboxyhemoglobin / Concentration |
| `oxygen_saturation` | 1 | Physiology / OxygenSaturation |
| `aorta_sodium_mEq_L` | mEq/L | LiquidCompartment / Aorta / Sodium / Molarity |
| `ambient_co_fraction` | 1 | GasCompartment / Ambient / CarbonMonoxide / VolumeFraction |
| `ambient_oxygen_fraction` | 1 | GasCompartment / Ambient / Oxygen / VolumeFraction |
| `total_fluid_mL` | mL | Physiology / TotalFluidVolume |
| `alveolar_ventilation_L_min` | L/min | Physiology / TotalAlveolarVentilation |
| `left_pleural_pressure_cmH2O` | cmH2O | GasCompartment / LeftPleuralCavity / Pressure |
| `left_pleural_volume_mL` | mL | GasCompartment / LeftPleuralCavity / Volume |
| `residual_blood_volume_mL` | mL | Action / TotalBloodVolume |
| `tube_flow_mL_min` | mL/min | Action / FlowRate |
| `source_flow_mL_s` | mL/s | Action / FlowRate |

各内部诊断不是要求每个分支每一时刻都存在。胸管/血胸 Action 请求在动作不存在或原生自动停止后可 unavailable；不得填零或推断控制成功。血胸原始微小负值保持。左胸腔 Pressure 是绝对区室压力，不当作跨肺压。脱水 TotalFluidVolume 与 BloodVolume 不同。

完整连续历史序列在内存中组织；示例 evaluation_excerpt 明确只截取首末帧供文档展示，不冒充完整序列。原始患者状态仅作为只读后端证据，不被整包复制到输出；出血源状态不是 Agent 生理值，也不当作临床检查结果。

FrozenReader 按 V2.1 基线 SHA 读取既有轨迹，不新建 Pulse Session、不重新设计 DataRequest。ResearchAccess 绑定患者及分支路径，显式选择诊断、事件、回执、源快照；权限由可信宿主提供，不是新鉴权平台。事件只保留读取语义：初始活动事件持续时间可表明窗口前已激活，不虚构精确首次发生时刻；.02 秒步后事件与原生日志时间差不改写。JSONL 缺少的时段不能推断没有事件。

match_pair 对控制/干预固定配置、患者身份及治疗前真实 values/diagnostics/events 进行匹配；1e−7 仅是既有确定性数据比较容差，不是 E/P/I 阈值。胸部两份确切初始化文字别名经过核对后可匹配，其余字段仍逐项一致。不支持任意病例拼接；匹配结果仅是对照适用性，不是疗效结果。

现有单伤 CSV 无 patient_id，回放仅使用显式文件病例标签，不能当成原生身份或加入跨患者正式对照。正式集成应使用已有会话/epoch/患者身份及检查结果上下文；这些不通过离线候选自动授予。

## B1 时间一致性补丁（2026-10-14，待重新审核）

模型采用输入校验，不重排、覆盖、平均或改写生理读数。单份 EvaluationObservation 的 frames.simulation_time_s 必须严格递增；同刻相同帧和同刻矛盾帧均拒绝，患者身份、Measurement 有效性及未来采样检查保持。没有新增 phase/sequence 字段。

原生事件、动作回执和源快照分别要求 observed_at_s 非递减；倒序拒绝。历史 30 条复合分支的原生事件文件均已按时间排列，因此不需要排序适配。相等时间仅表示同一观测时刻，不以列表位置推断真实因果顺序：

- events：不同名称的同刻事件全部保留；同一名称、同一时刻的 active 或 native_active_duration_s 不一致时拒绝，不能通过先激活后解除等任意排序消解。完全相同的事件记录保留。合法同刻不同事件按输入顺序保留，冻结读取对每次集合变化按名称排序，重复读取确定一致；名称排序不表示发生先后。
- 窗口开始时已激活的事件保留原持续时间，允许该持续时间表明起始于窗口前；不改写为窗口内首次激活，也不要求初始事件持续时间小于观察窗口长度。继续保留步后 observed_at_s 与原生日志的区别。
- actions：回执缺少动作对象/请求唯一标识，phase 不能充当对象身份。同刻所有回执（包含相同 phase、不同 state）逐条保留，不做去重或虚构先后；gaps 明确追加 `action order indeterminate at simulation_time_s=...`。这组记录只能证明各个回执存在，不能解释为同一对象的状态转换。不同时间的连续动作按原序保留。标记幂等，不重复追加；需要精确执行顺序时必须回溯原始证据，不足则不可确定。
- source_snapshots：每项代表该检查点的完整活动源集合，不是单对象增量。同刻快照的源集合不一致则拒绝；集合相同但列表排列不同可接受，两份原记录及各自顺序均保留。不同对象同时存在于同一快照的完整列表中，不会被合并删除。相同时间不支持未注明的多个阶段快照。

所有非递减/严格递增比较使用原始仿真时间值，不进行舍入、时间平移或近似时间合并；已有末端窗口容差保持不变。负责人已明确允许仅在历史读取适配层合并完全相同记录，规则如下。JSON Schema 仍是结构子集，正式使用必须通过 Python 语义校验和可信投影，N1 不在本轮修复范围。候选不因此自动冻结或接入 Runtime。

### 已批准的历史同刻重复采样适配

仅 load_branch 对同一患者、同一冻结分支的相邻同刻原始记录作严格相等比较。比较完整原始记录（包含隐藏诊断、事件、状态、采样时间和其他字段），使用排序键的严格 JSON 表示，禁止将 bool 与数字等 Python 相等关系当作原始一致；数值表示不同亦保守拒绝。任何差异拒绝，不对投影后恰好相等的记录合并。倒序仍拒绝，不排序或放宽模型。EvaluationObservation 直接输入仍拒绝所有重复时刻。

合并仅影响派生评价帧，原始文件和 SHA 不变；gaps 中的 `identical historical observation records merged` 审计记录包含 branch、patient_id、source_file、raw_records、merged_records、evaluation_frames，以及每个合并行的一基行号、代表行号、原始 simulation_time_s。读取器不写历史文件。原始扫描统计与派生评价帧数量分别报告；事件、动作、源快照不参与此合并。

授权、原始行号核对和前后测试记录均在 b1_fix_review；旧 final_review 作为修复前审核证据保持不变。当前为 B1 修复候选，尚未正式冻结。
