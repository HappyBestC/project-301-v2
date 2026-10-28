# 临时V1兼容配置

此目录不定义正式V2科研模型。两份YAML与清理前完全相同。

- `配置/injury_templates.yaml`：`contracts/casualty.py`动态生成旧CasualtyInput/KnownInjury；真实Treatment Agent的AgentCaseContext仍使用它。不能用新的十类配置替换后声称语义不变。
- `配置/battle_injury_patterns.yaml`：仅旧六模式兼容测试及反事实评价Demo读取。它不表示V2研究支持六类战伤，正式复合范围仍是五类固定AB。

`core301.paths.FROZEN_ROOT`仅为兼容别名，现指向本目录。旧8份说明文档已经移除。M3-A完成新版输出、Context和调用方迁移后再审查删除条件；不能仅升级输出schema便删除仍被旧执行器读取的模板。
