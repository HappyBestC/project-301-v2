# 证据路径导航

项目根目录：`/home/private/project-301/`。两个 JSON 文件清单的每个键均为根目录下的完整相对文件路径，值为归档时 SHA-256；可逐文件定位和校验。原始数据留在原位置，不删除或重新序列化。

最终验收证据根目录：`research_artifacts/v2_final_ten_injury_restricted_acceptance_v0.1/`（以下简称 F）。其既有 `validation/artifact_sha256.json` 锁定 1676 个文件，归档前已逐项核验；清单自身也由新基线索引。

| 内容 | 项目相对路径（F 表示上述目录） |
|---|---|
| 最终报告、矩阵、审查规范 | F/FINAL_REPORT.md；F/TEN_INJURY_ACCEPTANCE_MATRIX.md；F/ENGINEERING_ACCEPTANCE_SPEC.md |
| 最终机器审计、执行流水线 | F/validation/final_audit.json；F/validation/final_pipeline.json |
| 用户限定风险决定 | F/USER_RISK_ACCEPTANCE.json；F/ACCEPTANCE_DECISIONS_REQUIRED.md |
| 版本化准入证据、动作权限 | F/INTEGRATION/ADMISSION_MANIFEST.json；F/INTEGRATION/ACTION_ALLOWLIST.md；F/INTEGRATION/RUNTIME_INTEGRATION.md |
| 血胸数值规则及机制 | F/HEMOTHORAX/N1_FINAL_REVIEW.md；F/HEMOTHORAX/E1_FINAL_REVIEW.md；F/HEMOTHORAX/ADMISSION_RESULT.md |
| CO、低氧独立验收 | F/CO_EXPOSURE/ADMISSION_RESULT.md；F/ENVIRONMENTAL_HYPOXIA/ADMISSION_RESULT.md |
| 高钠诊断及两种初始化全部数据 | F/HEMOTHORAX/SODIUM_DIAGNOSIS.md；F/experiments/（含 frozen/、fresh/、轨迹、状态、日志、统计、图） |
| 807 单元测试 | F/validation/regression/unit_final.xml；F/validation/unit_final.log |
| 43 旧原生测试和旧七类 13 配对 | F/validation/regression/native.xml；F/validation/regression/phase1/；其余旧原生数据在 regression/hemothorax/、exposure/ |
| 3 新正式 E2E | F/validation/e2e/formal.xml；F/validation/formal_e2e.log；F/validation/e2e/formal/{hemothorax,carbon_monoxide_exposure,environmental_hypoxia}/ |
| 准入前真实验证 | F/validation/e2e/verify_hemo2.xml；F/validation/e2e/verify_exposure3.xml 及对应同名目录 |
| 失败、中断和重试 | F/validation/native_attempt_ledger.json；F/validation/superseded_interrupts.json；validation/ 内所有原始运行文件 |
| 历史保护、唯一授权旧源码变更 | F/validation/baseline.json；F/validation/protected_files_check.json；F/validation/authorized_route_change.json；F/validation/new_source_manifest.json |

Runtime 的风险符合度还依赖 `research_artifacts/v2_ten_injury_completion_program_v0.1/experiments/raw/` 中 `hemo/combined/observations.csv`、`runtime_attempt2/carbon_monoxide_exposure/base/observations.jsonl`、`runtime_attempt2/carbon_monoxide_exposure/treated/observations.jsonl`。这些文件及最终准入 manifest 不得修改或迁走。

`EVIDENCE_FILES_SHA256.json` 索引所有既有 `research_artifacts/`、`runs/`、`logs/`、`exports/`、`plan_effect_dataset/`、`冻结版/` 文件；涵盖此前能力审查、筛选、合同设计、Phase 1、Phase 2、血胸收尾及十类专项攻关。`PROJECT_FILES_SHA256.json` 进一步覆盖其他目录，包括 Pulse 原生文件、V1/V0.2、运行环境及 Batch500 文件。归档前最终审计记录：64891 个原文件未改、1 个既有 V2 入口经授权修改；Batch500 的 15639 个文件不变。本次归档不再修改任何既有文件。
