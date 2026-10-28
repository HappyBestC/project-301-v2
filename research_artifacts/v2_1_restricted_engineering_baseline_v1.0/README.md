# V2.1 五类典型战场复合伤受限仿真工程稳定基线 v1.0

**用户于 2026-10-14（Asia/Shanghai）确认最终验收 5/5；归档和只读完整性核验通过后，本阶段正式结束。**

基线标识：`301.v2_1.restricted.engineering.baseline.1`。正式范围仅五类固定 AB 联合救助方案，生产权限关闭。后续 LLM Agent 救助规划为独立阶段。

- [用户验收原文](USER_ACCEPTANCE.md)与[正式验收记录](ACCEPTANCE.json)。
- [五类配置](FIVE_COMPOSITE_CONFIGURATIONS.json)、[战场场景](BATTLEFIELD_SCENE_DESCRIPTIONS.md)、[固定协议与约束](FIXED_PROTOCOLS.md)、[真实动作及回执](FIXED_PROTOCOLS.json)。
- [版本](VERSIONS.json)、[快照来源与 SHA](SNAPSHOT_ORIGINS.json)及 snapshot/。
- [944 项测试证据](TEST_RESULTS.json)：853 旧测试 + 86 新单元/反例 + 5 最终原生 E2E；重复不累计。收尾轮实际重跑 898 项，本次归档未重跑测试或 E2E。
- [已接受风险与限制](KNOWN_LIMITATIONS.md)、[45 完整分支及全部失败证据导航](EVIDENCE_GUIDE.md)。
- [项目 SHA](PROJECT_FILES_SHA256.json)、[证据 SHA](EVIDENCE_FILES_SHA256.json)、[归档 SHA](ARCHIVE_SHA256.json)、[归档核验记录](ARCHIVE_VALIDATION.json)、[只读核验脚本](verify.py)。

历史报告的 NOT_RECORDED/PENDING 或 stage_closed=false 保留生成时语义，本新增验收记录登记之后的用户确认和阶段关闭，不改写 Runtime 固定引用的原证据。四项生理风险仍存在，不等于临床安全认证或完全治愈。

大型原始证据、Pulse 二进制及环境保留在项目原位置，由清单锁定；迁移需保留这些相对路径。快照不含 .env 密钥。SHA 清单提供完整性校验，不声称外部数字签名。

```bash
python research_artifacts/v2_1_restricted_engineering_baseline_v1.0/verify.py
```

脚本仅使用 Python 标准库，不启动原生引擎、不写文件。后续新增文件不影响当前固定清单；不得刷新清单掩盖已验收源码、协议或历史证据的更改。后续工作另建版本目录并引用本基线。
