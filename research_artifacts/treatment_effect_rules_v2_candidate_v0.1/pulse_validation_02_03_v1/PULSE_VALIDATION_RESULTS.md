# V2E-02/03 真实 Pulse 验证结果

仅运行新 campaign `batch1_02_03_v1` 的两支 Treatment；旧 `batch1_r2/external_s0.4_zero` 及其共享治疗前状态只读复用。无新 Control、无重试。

|规则|运行状态|治疗前CO (L/min)|Treatment末窗CO均值 (L/min)|zero末窗CO均值 (L/min)|相对zero逐点增量均值/最小值|M/F|研究等级|安全状态|
|---|---|---|---|---|---|---|---|---|
|V2E-02|ARCHIVED|5.923580|6.456997|5.925365|8.972392% / 7.899700%|True/True|E|UNRESOLVED|
|V2E-03|ARCHIVED|5.923580|6.458702|5.925365|9.001163% / 7.910116%|True/True|E|UNRESOLVED|

增量逐点计算 `(Treatment CO − zero CO) / zero CO × 100%`，再取末窗均值；M为均值≥2%，F还要求全窗≥6%。最终等级来自未修改的V1.0 AST。末窗采用原评价器选择的420–480秒实际采样，端点浮点值保留。

## V2E-02

- 原生事件名称：['StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale']；严重事件：[]；必需安全缺测：[]。
- 原始数据与日志：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/batch1_02_03_v1/external_s0.4_zero_saline/`（raw_requests.jsonl、raw_native_events.jsonl、raw_actions.jsonl、pulse.log、capture、execution_receipt.json、SHA256.json）。
- 180秒按原顺序先RightLeg停源，再给予Saline，袋量500 mL、速率100 mL/min；480秒结束。袋量不作为实际入体量。
- 两项原生动作 accepted：[True, True]。
- MAP (mmHg)：治疗前 94.47739688899897；Treatment末窗均值 95.254456；zero末窗均值 94.586305。
- HR (1/min)：治疗前 88.42598130162689；Treatment末窗均值 76.322446；zero末窗均值 88.587311。
- Hb (g/dL)：治疗前 14.94583200370689；Treatment末窗均值 13.753524；zero末窗均值 14.912558。
- BV (mL)：治疗前 5311.9640066427655；Treatment末窗均值 5772.611985；zero末窗均值 5323.809590。
- 独立安全输出完整保存在该分支 evaluation.json，UNRESOLVED不等于安全通过。
- 原生执行回执 SHA256：`a489b819fe38ccb5a9bbc07d8fd3b07e27d013881d38f6a13719140964215bda`。

## V2E-03

- 原生事件名称：['StartOfCardiacCycle', 'StartOfExhale', 'StartOfInhale']；严重事件：[]；必需安全缺测：[]。
- 原始数据与日志：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/batch1_02_03_v1/external_s0.4_zero_blood/`（raw_requests.jsonl、raw_native_events.jsonl、raw_actions.jsonl、pulse.log、capture、execution_receipt.json、SHA256.json）。
- 180秒按原顺序先RightLeg停源，再给予Blood，袋量500 mL、速率100 mL/min；480秒结束。袋量不作为实际入体量。
- 两项原生动作 accepted：[True, True]。
- MAP (mmHg)：治疗前 94.47739688899897；Treatment末窗均值 95.255865；zero末窗均值 94.586305。
- HR (1/min)：治疗前 88.42598130162689；Treatment末窗均值 76.341535；zero末窗均值 88.587311。
- Hb (g/dL)：治疗前 14.94583200370689；Treatment末窗均值 14.905183；zero末窗均值 14.912558。
- BV (mL)：治疗前 5311.9640066427655；Treatment末窗均值 5772.610355；zero末窗均值 5323.809590。
- 独立安全输出完整保存在该分支 evaluation.json，UNRESOLVED不等于安全通过。
- 原生执行回执 SHA256：`c28716398913192332837e3c9a4d6625636348f43d9c0a1f64ed23b8d5b7ed2f`。

## 修改和测试

- 运行代码仅修改 driver.py：增加窄范围 EXTERNAL_ZERO_REFERENCE.json 只读解析/校验；gate、response、evaluate分别使用旧归档依赖、治疗前状态和zero补充证据。其他执行器、规则、AST、阈值和患者未修改。
- 更新代码完整性清单中的driver SHA及关联清单SHA；旧实验及其补充证据不变。
- 新增11项针对性测试通过；使用已有隔离回归入口运行99项驱动回归（包含32支Mock和18组比较），结果见CURRENT_REGRESSION_RESULTS.json。
- 首次直接unittest discover因历史输出目录冲突及旧合成参考算法身份报错（9失败、18错误）；原日志保留。改用既有隔离入口重新生成合成参考并完整执行，无删除测试或放宽断言。
- 1091份保护文件SHA未变，旧zero及Control完整保留；新原生归档SHA均通过。

## 实际执行命令

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --campaign batch1_02_03_v1 --single external_s0.4_zero_saline --execute
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --campaign batch1_02_03_v1 --single external_s0.4_zero_blood --execute
```

两条命令按顺序单独执行，第一条归档且无技术/严重安全停止条件后才运行第二条。已有运行ID不可重复执行。没有开展其他原生实验，未启用生产评分。

本轮原生执行次数为2（补液1、输血1），均ARCHIVED且review_required=false。两条新结果重新通过同一AST离线复算，结果逐字段一致。研究等级E不代表整体安全或临床治愈。当前无02/03执行技术阻塞。
