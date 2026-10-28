> **历史记录：迁移时状态（2026-10-19，科研清理之前）。** 本文数字与路径不代表当前目录；最新清单见RESEARCH_CLEANUP_REPORT.md。原迁移清单/通过日志已隔离至research_baseline/history/migration，早期失败日志及原横向全树索引在清理恢复档案中。

# 迁移清单与完整性

来源：`/home/private/project-301`。目标：`/home/private/project-301-v2`。2026-10-19。

目标开始时不存在；没有覆盖既有用户工程。先审查源码import、配置/manifest引用与M2-C准确测试集，再执行选择性复制。没有复制整项目后删除。原目录未删除、移动或覆盖文件。

## 文件与模块口径

迁入来源文件 **870** 个，合计 **648,987,702字节**；其中868个原样复制，2个必要适配。core301共121个文件，其中112个Python模块文件，涉及9个一级子包：agent、context、contracts、dispatch、evaluation、fixtures、observation_candidate_v2、pulse、runtime；另保留顶层cli/paths/__init__。

这870个不包含新建说明/验证日志/虚拟环境，也不包含外部Pulse安装。最终交付文件共910个（含新文档、脚本、验证证据与DELIVERY_SHA256.json，不计venv、editable安装元数据和外部Pulse）；DELIVERY_SHA256.json记录其余909项最终SHA。外部运行时311个必要运行文件加1份许可证，约20 MB。原样迁入资料约649 MB，主要体积来自原准入强制校验的研究证据；不能在不改业务准入逻辑的前提下随意删去。原全量research_artifacts约24 GB未迁移。

## 逐文件权威记录

- `research_baseline/MIGRATION_SELECTION.json`：每个迁入文件的相对源/目标路径、分类、保留理由、source_sha256、target_sha256和复制方式。相同相对路径对应上述两个根。
- `research_baseline/SOURCE_DISPOSITIONS.json.gz`：原114127个文件/链接逐项的分类与理由，包括未迁移项；分类按已审查的当前运行范围，不代表每份历史实验都做了科研内容评价。
- `research_baseline/SOURCE_BEFORE.json.gz`：迁移前完整文件目录记录；初选835个文件做SHA，其余做大小/mtime_ns或软链接目标记录。不要将元数据核对称为全树SHA审计。
- `validation/source_protection.json`：原树无新增、无缺失、无内容哈希/元数据变化。
- `research_baseline/PULSE_INSTALL_MANIFEST.json`：外部软件文件哈希、来源与安装范围。

## 分类和决策

| 分类 | 迁移决策与具体依据 |
|---|---|
| REQUIRED | Agent/provider/prompt、合同、runtime、dispatch全链路与Pulse适配；正式config、TEN/FIVE范围、Catalog fixture；必要tests和测试fixtures；原生准入引用的证据。实际import审计及1028测试验证闭包 |
| COMPATIBILITY | V1 contracts、冻结版/v1模板及八动作说明、旧ResourceManager、旧runtime和评价模块；旧合同、ETA、TaskEvent和现有真实Treatment LLM仍依赖 |
| RESEARCH_REFERENCE | M1/M2-A/B/C报告与版本、单伤/复合冻结摘要、新观测契约/schema、十四规则与后续真实Pulse摘要；保留历史结论，不重复保存整套snapshot |
| OPTIONAL | 旧scripts/docs可供历史追溯；新工程提供替代启动/验证文档。完整observation_candidate_v2历史回放测试需额外轨迹，不属于678集合，保留schema和实现但不复制全部回放数据 |
| EXCLUDED | pulse_batch/pulse_batch_parallel及测试（不被core301导入）；500条/随机批量数据、候选规则、旧R01—R14冻结包、重复snapshots、导出zip、日志大库、notebook、旧venv/cache/build和真实.env。旧核心评价器仅因接口兼容保留，未替代正式V2E规则 |
| EXTERNAL_DEPENDENCY | Python3.11、requirements.lock.txt所列新安装依赖、独立最小Pulse4.3.2运行时；不引用旧工程Python源码或业务配置 |

## 为什么仍有research_artifacts路径

`runtime/v2/restricted_admission.py`读取冻结manifest及其8份证据；`runtime/v2_1/admission.py`逐项检查588个proof文件，其中3个Pulse文件转由外部软件路径提供，其余保持原相对路径与哈希。原manifest、控源/血胸/环境风险证据和配置都不改。依赖集合包含部分历史日志、状态与验证脚本：它们是运行时哈希校验的数据，不作为新工程实验入口运行。

另补齐tests/v2_1动态拼接的20个runtime_final观测、事件、日志和endpoint fixture。它们服务既有风险正/负测试，不能为减少体积而删除测试。

14条V2E规则保留原adapter/common/reference/calibrate/offline/candidate_eval/healthy_analysis依赖链。旧draft参数文件仅供内部兼容读取，不成为正式规则权威；全历史load_case批量重放数据不迁移。旧科研脚本中的归档路径文本可作为来源记录存在，不属于活跃入口读取依赖。

## 必要适配（仅新工程）

1. `src/core301/cli.py`：历史默认`patient-test/casualties_v1.json`在原工程已不存在；缺失时回退到已有`src/core301/fixtures/casualties_v1.json`。显式参数/存在的原默认文件仍按原逻辑，医学Prompt不变。
2. `pyproject.toml`：增加Pulse可选依赖protobuf5.29.2/numpy2.4.6；pytest使用importlib解决同名test_integration模块，测试pythonpath补tests以保留已有helper import；默认只收集tests，排除integration。未修改测试断言。
3. 新增activate/configure脚本、锁定依赖和验证脚本。`pulse`是指向独立运行时的唯一业务树外部链接；不是旧源码/配置链接。既有paths.py和准入代码不变。

两项迁入文件适配的前后SHA详见MIGRATION_SELECTION.json；其余868项完全相同。任何冻结文件未调整。所有源码Prompt、M2实现和冻结规则文件均原样。

## 外部依赖与可复现范围

新venv由`/root/miniconda3/envs/a301/bin/python`创建，Python3.11.15，系统site-packages关闭。业务依赖pydantic2.12.3、ruamel.yaml0.19.1、openai2.54.0、python-dotenv1.2.4、pytest8.4.2，Pulse绑定protobuf5.29.2、numpy2.4.6；所有传递版本见requirements.lock.txt。

Pulse现有多个4.3.2构建的二进制SHA不同，不能直接切换后绕过冻结校验。因此将原已验证构建中必要的库/绑定/状态/数据选择性安装至`/home/private/pulse-4.3.2-301-runtime`，约20 MB，没有复制完整安装树、SDK、驱动程序、Java、模型集合或研究数据库。其来源为旧工程内第三方Pulse发行产物，安装完成后运行不读旧树。跨机器需提供相同构建产物并核验安装清单；本轮未验证从互联网重建完全相同二进制。

源码配置独立、Python依赖环境独立、外部软件依赖三层分别成立；这不是声称项目无外部软件依赖。版本锁未包含供应链wheel内容hash，不等同离线安装包仓库。
