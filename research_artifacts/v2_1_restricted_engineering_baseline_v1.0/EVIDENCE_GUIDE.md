# 证据导航

所有 `research_artifacts/...`、`src/...` 路径均相对项目根。`snapshot/` 保留同样相对路径的源码和关键报告副本；大型原始数据在原位置按 SHA 固定。

| 内容 | 路径 |
|---|---|
| 正式用户验收与阶段关闭 | 本目录 USER_ACCEPTANCE.md、ACCEPTANCE.json |
| 当前正式准入 | research_artifacts/v2_1_battle_composite_injuries_v0.1/validation/admission_v2.json |
| 本阶段最终结论及历史待验收状态 | 同研究目录 FINAL_REPORT.md、FIVE_CASE_ACCEPTANCE_MATRIX.md、validation/final_audit_v2.json；生成时的待用户验收字段不回写 |
| 全部 47 次尝试 | 同研究目录 validation/branch_ledger_v2.json；45 完整、2 部分 |
| 原始对照/干预 | 同研究目录 experiments/raw/stage1/、stage2/、thoracic_timing_v2/、dehydration_pair_retry/ |
| 初次 Runtime 关闭回执失败 | 同研究目录 experiments/raw/runtime_repeat/{0..4}/；validation/runtime_attempt1_provenance_correction.json |
| 修复后的早期 Runtime | 同研究目录 experiments/raw/runtime_final/{0..4}/ |
| 最后五条真实新门控 E2E | 同研究目录 experiments/raw/runtime_risk_v2/{0..4}/ |
| 测试 XML、日志及计数口径 | 本目录 TEST_RESULTS.json；对应项目根路径及 snapshot 副本 |
| 四项固定风险及独立复核 | 同研究目录 USER_COMPOSITE_RISK_ACCEPTANCE.2026-10-13.1.json、validation/risk_review_v2.json、OBSERVATION_AND_SAFETY_RULES.v2.md |
| 完整旧证据导航 | 同研究目录 validation/evidence_index.md、evidence_index_v1.md |
| 原生二进制、初始化身份 | 本目录 VERSIONS.json；全工程 SHA 清单 |

所有既有研究文件均列入 EVIDENCE_FILES_SHA256.json，包括失败/被拒绝/部分尝试、配置、状态、事件、观测、动作、Journal、资源、日志和测试产物；不只筛选成功记录。PROJECT_FILES_SHA256.json 覆盖归档前全部工程文件，包含 V1、V0.2、Batch500、V2.0、原生引擎及环境。ARCHIVE_SHA256.json 覆盖本目录除清单自身外的归档文件。

本次归档只进行只读校验；不运行测试、不启动 Pulse、不追加分支。45 条完整响应预算已经耗尽。可独立使用标准库执行 `python research_artifacts/v2_1_restricted_engineering_baseline_v1.0/verify.py`，无须导入 Runtime 或安装 Pulse Python 依赖；完整核验仍需原项目证据和相对路径。本目录不是脱离项目的可执行发行包。
