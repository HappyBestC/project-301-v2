# V2 十类基础伤情受限仿真工程基线 v1.0

**已由用户于 2026-10-13（Asia/Shanghai）明确验收通过，10/10；本阶段正式结束。**
基线标识：`301.v2.restricted.engineering.baseline.1`。生产权限保持关闭。

本次验收仅覆盖 V2 基础伤情模型、固定救助协议、Pulse 4.3.2 执行、合法观测和统一受限 Runtime 工程能力。临床安全认证、真实 LLM Agent 规划效果、复杂多伤情组合及整个 301 项目最终验收均不在范围内。

- [用户确认原文](USER_ACCEPTANCE.md)及[正式验收记录](ACCEPTANCE.json)：新增的最终验收依据。
- [十类配置](TEN_INJURY_CONFIGURATIONS.json)及[固定协议说明](FIXED_PROTOCOLS.md)：封存名单、级别、位置、动作和时序。
- [版本登记](VERSIONS.json)：版本常量、原生二进制和初始化身份；[源码快照来源](SNAPSHOT_ORIGINS.json)对应 `snapshot/` 内 133 个文件。
- [测试登记](TEST_RESULTS.json)：807 项单元测试、43 项旧原生测试、3 项新增正式原生 E2E，共 853 项通过。旧七类 13 个配对配置的历史对照最大差值为 0.0。
- [已知限制](KNOWN_LIMITATIONS.md)及[证据导航](EVIDENCE_GUIDE.md)。
- [全部既有文件清单](PROJECT_FILES_SHA256.json)及[研究证据清单](EVIDENCE_FILES_SHA256.json)：项目相对路径 → SHA-256，涵盖原始结果、事件、轨迹、状态、失败和中断尝试。
- [归档完整性清单](ARCHIVE_SHA256.json)、[归档时核验结果](ARCHIVE_VALIDATION.json)及[核验脚本](verify.py)。

既有实验和测试结果中的 `NOT_RECORDED`、历史模块中的 `PENDING` 表示生成当时的状态，原件不回写。本目录的用户确认记录登记其后的最终工程验收；统一受限 Registry 是当前路由准入依据。风险记录和 Runtime 钉住的准入证据保持原始字节。

原始大型证据、Pulse 二进制及运行环境保留在项目原位置，并由清单锁定；本目录不是脱离项目即可运行的独立发行包。迁移时须保留清单所列文件及相对路径。快照不包含 `.env` 密钥内容。

后续研究另建版本及证据目录，引用本基线标识；不得覆盖本基线、篡改历史证据或原地更改已验收固定协议。本次归档没有新增伤情、修改协议、修改源码或重跑生理实验。

在项目中运行只读完整核验：

```bash
python research_artifacts/v2_restricted_engineering_baseline_v1.0/verify.py
```

完整核验对既有文件的任何变更均报告差异；后续新建文件不影响本清单。版本化开发引起的差异应独立解释，不能通过重写本基线消除。
