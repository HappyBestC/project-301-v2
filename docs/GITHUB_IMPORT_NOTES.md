# GitHub 首次导入说明

本地仓库准备日期：2026-10-27（America/Chicago）。默认分支为 `main`。

## 纳入范围

本次导入保留项目源码、测试、配置、文档、数据集、冻结研究档案、实验结果及历史验证记录，包括新生成的 [项目文档报告](PROJECT_OVERVIEW_REPORT_ZH.md)。

`.gitignore` 排除本机 `.env` 及其变体、虚拟环境、缓存、构建产物、临时 `runs/` 和外部 Pulse 运行时链接；空配置模板 `.env.example` 保留。`.gitattributes` 禁止 Git 自动转换换行，保护研究证据的字节级 SHA-256。

克隆后需要按根 README 重建 Python 环境，并单独配置兼容的 Pulse 4.3.2 运行时。项目内仍有历史绝对路径，相关隔离检查与部分工具的跨机器适用性需要按目标环境复核。

## 已发现的基线清单差异

上传准备时执行 `python -B scripts/verify_baseline.py`，发现旧清单中的一个文件哈希与当前源码不同：

| 文件 | 旧清单 SHA-256 | 当前 SHA-256 |
|---|---|---|
| `src/core301/runtime/v2/case_runtime.py` | `9ef93b36553bbb36c36b51f3324823f2d8d2ee3fdb7cb5622f6b7d975abd249e` | `ee08773176dfc3472996abcd262820b6a5e460bdca8b451a152b400f35cd0b00` |

这一源码修改已在 M3-C2 的 [变更审计](m3c2_feedback_decision/validation/change_audit.json) 和 [架构说明](m3c2_feedback_decision/ARCHITECTURE.md) 中记录：提取默认治疗时间检查方法，以支持独立动态时序子类。旧 `research_baseline/CURRENT_RESEARCH_FILES.json` 尚未反映该阶段变更。

本次导入保留现状，不修改源码或回写历史清单。因此，现有 `scripts/validate.sh` 运行到旧基线完整性检查时仍会遇到该差异；这与 Git 文件传输是否成功是两个独立问题。

报告编制时执行的六组 M3/最小闭环只读核验全部通过，具体范围见 [报告第 9 节](PROJECT_OVERVIEW_REPORT_ZH.md#9-测试与本次实际核验)。本次上传准备未重新运行完整测试套件或真实模型实验。
