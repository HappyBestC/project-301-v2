# 301医疗资源与能力模型V1.0 — M1设计交付

2026-10-19（Asia/Shanghai）。已完成现状盘点、文献核对与模型设计；新增内容仅在本目录。没有修改Agent、伤情配置、治疗/Pulse映射或14条锁定规则，没有运行Pulse，也未实现M2。

## 阅读入口

| 文件 | 内容 |
|---|---|
| [CURRENT_ACTION_INVENTORY.md](CURRENT_ACTION_INVENTORY.md) | 十类基础伤情、五类复合伤、12正式动作、保留动作、执行范围和来源索引 |
| [ACTION_RESOURCE_MAPPING.md](ACTION_RESOURCE_MAPPING.md) | 全动作能力/人员/设备/耗材/地点映射，逐层证据标记 |
| [RESOURCE_MODEL_V1_DESIGN.md](RESOURCE_MODEL_V1_DESIGN.md) | 六实体字段、关系、静态/动态边界、M2接口与取消/失败语义 |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | 18项证据缺口与待确认输入、后续文献查证队列 |
| [VALIDATION.md](VALIDATION.md) | 本轮文档覆盖、引用和源码/快照只读一致性核对结果 |

另提供中文文件名[《301救助动作—医疗能力—资源需求映射表》](301救助动作—医疗能力—资源需求映射表.md)入口，正文只有一份。

## 设计结论

- 正式受限动作共12个，全部进入映射。`inhaled_albuterol`为合同保留项，未开放；旧phase-1的血胸保留状态不能覆盖后续独立受限准入；环境移除有专用路径，不能因通用动作枚举缺项而遗漏。
- 三类控源动作通过修改原生伤情源Severity实现，是后端研究代理。环境移除通过环境条件修改实现，不能等同已模拟患者转运。
- 已有单病例研究stock/holds/permissions及设施/车/队字段；缺少共享资源身份、真实技能资质、物料规格和多伤员统一状态。研究人数与包数只确认代码事实，不能当作临床必要配置。
- 采用Resource、MedicalCapability、MedicalOrganization、MedicalFacility、TransportAsset、TreatmentRequirement六实体。能力由人员/设备/物料/地点条件共同满足；组织归属与当前位置分开，Role仅作标签。
- M2建议基于同run共享状态、Allocation和事件记录开发；预留必须原子检查，持续占用、已消耗和未知执行分别处理。未知资格、数量和时间返回INDETERMINATE，不填默认值。

## 依据与当前局限

项目主要依据是V2/V2.1已验收配置、执行器及资源fixture；出处与定位符号详见盘点S01—S29。外部依据已实际读取[官方AJP-4.2 2026年版](https://assets.publishing.service.gov.uk/media/6a5e04dba3c718d2556d08b3/AJP_4_2_EdA_V1_NATO.pdf)第6—8章，精确条款/页码见模型设计。浏览工具后续取页曾超时，改由官方地址下载至临时目录并解析正文完成核验；本目录记录来源摘要，不存整本PDF。

14条V2E锁定规则与后续真实Pulse研究证据已定位；旧R01—R14同名冻结包是另一来源，未混用。后续09报告记载14/14首轮AST输出为10 E、3 P、1 I；该I与活动瞬间流率缺测有关，不能解释为治疗无效或14条全通过。M1不改变任何评价结果。

真实人员资质/人数、术式对应设备、血制品兼容和储运、设施条件、持续监护及处置时间仍需核定。目前没有已确认可互换的现实资源组合。TCCC及专科/产品规范仅列查证队列，未伪装成已核验医学标准。

下一阶段建议先确认最小场景实例、共享时钟及旧接口桥接，随后另行开发M2共享资源状态与冲突返回；本次交付停留在M1。
