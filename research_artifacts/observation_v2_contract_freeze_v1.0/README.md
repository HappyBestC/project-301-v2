# Observation v2 数据契约工程冻结归档 v1.0

**ARCHIVE_VERIFIED / USER_ACCEPTANCE_PENDING / NOT_ACTIVATED**。日期 2026-10-14（Asia/Shanghai）。

基线 `301.observation.v2.engineering.baseline.1`；患者契约 `301.patient_observation.frozen.v2`；评价契约 `301.evaluation_observation.frozen.v2`。

工程归档固定 15 项指标、Measurement、单位/来源/授权边界及 B1 后时间规则。不是 Runtime 接入、医学审批或 E/P/I 规则完成。用户已授权创建工程档案，尚未最终签收此档案；生产关闭。

阅读顺序：FINAL_FREEZE_REPORT.md、两个 *_FROZEN.md、KNOWN_LIMITATIONS.md、VERSIONS.json。源码依据在 snapshot/，旧候选及全部失败记录在 evidence/candidate/；其中 final_review 的 REJECT_PENDING_FIX 是修复前历史结论，当前以 B1 最终报告与 snapshot 最新源码为准。

schemas/ 中三个候选文件按字节保留；FIELD_DEFINITIONS.json 补充中文名、类型、单位、来源和门控索引。**JSON Schema 不能单独替代 Python 语义校验和可信投影**。冻结标识是归档标识，未修改源码或 payload 的候选版本字符串。

仅核验（不运行测试、Pulse、Agent，不写任何文件）：

```bash
python3 research_artifacts/observation_v2_contract_freeze_v1.0/verify.py --project-root /home/private/project-301
```

完整核验需要项目原始证据与 DEPENDENCIES.json 所记录的 Python 环境；可通过 `--environment-root` 指定同内容依赖根。该档案不是脱离项目即可运行的发行包。核验器本身仅标准库。

ARCHIVE_SHA256.json 覆盖归档文件；其自身摘要由核验输出给出，validation/VERIFY_RESULT.json 为不参与输入校验的独立输出收据，避免循环哈希。源码/来源 SHA 在 SOURCE_ORIGINS.json，外部证据在 EXTERNAL_PROJECT_SHA256.json，历史基线清单在 PROTECTED_BASELINES.json。首次构建脚本负责写入；verify.py 不刷新任何清单。

归档后不得直接覆盖；修改需独立新版本。用户验收确认后再单独决定后续工作，本轮不自动开始十类效果规则制定。

只读核验器首次因项目历史清单中的虚拟环境符号链接越界检查失败，收据保留在 validation/VERIFY_FIRST_ATTEMPT.json。现仅对已固定 SHA 的历史基线清单允许核验其符号链接目标，仍要求内容 SHA 一致；归档内部与普通来源路径不允许越界。没有放宽内容完整性校验或修改旧清单。
