# 301 V2科研工程清理报告

**RESEARCH_PROJECT_CLEANUP_PASS** · 2026-10-19（Asia/Shanghai）。本工程定位为个人硕士MAS科研工程，与横向project-301独立演进。本轮完成审查、清理、兼容路径适配、实际验证和文档更新，未进入M3。

## 清理前后实测

统计口径：工程内实际普通文件，不跟随目录软链接；排除.venv和独立Pulse安装，也不计工程外恢复档案。总大小为文件st_size合计（逻辑字节，不将其冒充含目录元数据/文件系统分配块的du值）。新审计清单、历史迁移证据、空实验目录占位文件和本报告均计入。

| 指标 | 清理前 | 清理后 |
|---|---:|---:|
| 项目普通文件数 | 910 | 923 |
| 项目总大小（不含venv，字节） | 652,750,974 | 651,557,374 |
| 总大小（MiB） | 622.512 | 621.374 |
| 根目录历史V1说明文档 | 8 | 0 |
| 已确认历史横向文件（8份旧说明+2份无用病例批次） | 10 | 0 |
| core301 Python模块文件 | 112 | 112 |
| core301一级子包 | 9 | 9 |
| 科研单元回归通过用例 | 1028 | 1028 |
| 其中M2核心回归 | 678 | 678 |
| 原生integration未执行 | 26 | 26 |

净文件变化 **+13**，净逻辑字节变化 **-1,193,600**。本轮移除19个文件共2,891,550字节，原样移动17个文件；新增科研说明、逐文件审计、实验目录占位和新运行证据，所以净变化不等于删除数量。清理目的为隔离历史依赖，并非追求最少文件数。历史横向计数采用上述已确认清理集合，不把V1字符串、医疗队/车辆代码或必要科研证据武断归为横向冗余。

research_artifacts仍约621 MiB：复合准入逐项检查588个proof，其中3份为独立Pulse软件；单伤准入检查8项evidence。此外还有风险测试的保存轨迹、正式规则/观测和必要来源记录。其余看似旧日志/状态/脚本仍在这些约束内，未修改冻结机制来减小目录。历史快照索引虽然覆盖旧路径，仍有冻结/评价来源关系，保留且不作为新实验启动入口。

## 清理清单与可恢复性

清理前已生成`research_baseline/cleanup/CLEANUP_PLAN.json`，逐项包含相对路径、文件类型、SHA、动作、理由、引用核查和恢复位置。先验证/保存原件，再按精确白名单unlink或rename；没有对未知目录执行rm -rf。

| 移除文件 | 分类 | 依据 |
|---|---|---|
| `冻结版/v1/冻结契约总览.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/TreatmentPlan_v1_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/10类基础伤情模板_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/PatientObservation_v1_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/6类典型战伤模式_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/Frozen_v1_契约一致性检查.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/AgentCaseContext_v1_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `冻结版/v1/冻结/最小伤员数据模型_v1_冻结版.md` | HISTORICAL_REFERENCE | V1 development prose; no source/test/config loader reads Markdown; superseded by research baseline and compatibility audit |
| `src/core301/fixtures/casualties_v2.json` | HORIZONTAL_ONLY | Unused historical milestone batches: no runtime/test name reference, CLI uses casualties_v1/first_case/first_plan; snapshot origins are provenance, not active proof pins |
| `src/core301/fixtures/casualties_v3.json` | HORIZONTAL_ONLY | Unused historical milestone batches: no runtime/test name reference, CLI uses casualties_v1/first_case/first_plan; snapshot origins are provenance, not active proof pins |
| `validation/all_unit_missing_dependencies.log` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `validation/all_unit_missing_dependencies.xml` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `validation/all_unit_initial_collection_error.log` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `validation/all_unit_initial_collection_error.xml` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `validation/all_unit_importlib_helper_error.xml` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `validation/all_unit_importlib_helper_error.log` | REDUNDANT | Resolved migration intermediate failure output; final migration results and report retained; reversible external archive |
| `research_baseline/SOURCE_BEFORE.json.gz` | HISTORICAL_REFERENCE | Inventory of original horizontal project, not current research dependency; migration summary retained and full record recoverable externally |
| `research_baseline/SOURCE_DISPOSITIONS.json.gz` | HISTORICAL_REFERENCE | Inventory of original horizontal project, not current research dependency; migration summary retained and full record recoverable externally |
| `research_artifacts/resource_model_m2a/DELIVERY_SHA256.json` | REDUNDANT | Historical M2-A delivery checksum index, no runtime/test/frozen admission/locked evaluator read; actual M2-A source and tests stay |

完整移动清单见同一计划：两份YAML迁至config/compatibility/v1/配置；12份迁移最终验证记录迁至research_baseline/history/migration/validation；原MIGRATION_SELECTION、MIGRATION_STATS和DELIVERY_SHA256迁至history/migration。移动文件SHA全部一致。

恢复档案：`/home/private/project-301-v2-cleanup-archive-20261019/original/`。19个移除文件、17个移动文件及修改前的文档/脚本/paths均保留可核验原件；BEFORE_FILES.json记录完整清理前SHA。该档案仅用于恢复，不在运行路径或测试fixture路径中。能从横向原件恢复的项目在计划中标注original_project_same_bytes；不修改横向原件。

所有保留/清理分类在FILE_CLASSIFICATION.json；新的组织/验证文件在NEW_FILES_CLASSIFICATION.json。DEPENDENCY_GRAPH.json记录源码及测试import、两套准入哈希边和兼容YAML加载方；ADAPTATIONS.json列本轮前后SHA。CURRENT_RESEARCH_FILES.json是当前运行完整性权威，不再用旧870迁移清单要求历史文件永远留存。原科学冻结manifest原样保留，未用新清单替代其准入验证。

## 兼容适配与技术债

唯一修改的core301源码为paths.py：LEGACY_COMPATIBILITY_ROOT指向新兼容目录，FROZEN_ROOT继续作已有API别名。两份YAML完全未改。源包内部未搬动、重命名或重写，所有测试源码SHA相同。

八份V1说明不被运行代码读取，已移除。V1 CasualtyInput、AgentCaseContext、PatientObservation、八动作TreatmentPlan及其Provider/Prompt/Context构建仍被真实救助链路使用；旧医疗队/车/机构/ETA/TaskEvent被M2协调器复用。旧反事实评价器和其fixture维持当前验证及研究对照基础，不能误称已接通V2E在线评价。逐项调用方和退出条件见LEGACY_DEPENDENCY_AUDIT.md；M3-A升级后还需核对Context和执行方，不能只改输出schema便删旧模板。

未发现可独立移除且只服务Unity的Python模块。纯横向闲置病例批次已删；目前保留的旧基础实现有实际研究调用者或必要测试，明确登记兼容债务，不以文件起源判无用。

## 正式科研能力与冻结状态

- 十类受限单伤、五类固定复合AB、十二动作及原部位/严重度/环境/固定参数全部保留。
- M1映射、M2-A统一共享账本、M2-B协调器及M2-C完整合同桥接仍可运行；未增加第二份库存或临床参数。
- Pulse4.3.2初始化、观测和原专用动作适配保留。工程StandardMale与后续Soldier研究证据按原范围分开，不扩展患者群体。
- 14条V2E-01—14保持RESEARCH_RULESET_V1_LOCKED；SHA `6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`，canonical参数和定义SHA均通过。原AST、参考提取算法和必要来源保留，未重写阈值/公式。
- 两个Agent原Prompt/Provider均未改；真实Treatment LLM仍V1输出。完整十二动作输入来自研究fixture或显式桥接，不能说真实LLM已支持全动作方案。

## 本轮实际验收

在新工程目录清除继承PYTHONPATH后执行：

```bash
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 bash scripts/validate.sh
```

该脚本source新activate后执行：

```bash
python -m pytest -q tests/complete_dispatch tests/shared_dispatch tests/shared_resources tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -p no:cacheprovider --junitxml=validation/m2_baseline.xml
python -m pytest -q tests -m 'not integration' -p no:cacheprovider --junitxml=validation/all_unit.xml
python -m core301.dispatch.shared_resources.demo
python -m core301.dispatch.shared_demo
python -m core301.dispatch.complete_demo
python scripts/verify_baseline.py
python scripts/check_demos.py
python scripts/pulse_smoke.py
```

实际678通过（12.94秒）；全量1028通过（41.69秒）、0失败、26 integration deselected、6条既有pkg_resources弃用警告。两组不相加。test_reconciliation.json逐个比较前后JUnit classname/name集合：新增0、删除0、核心减少0；测试断言/源文件均未改，未删失败测试，也未放宽校验。

858项当前依赖哈希核对通过；三单伤准入、五复合准入和Catalog的10/5/12覆盖均通过。三Demo共14/14/2条记录：A成功预留、B竞争失败、释放后B成功，完整胸部三动作无损传递，完整计划版本0→1与1→1；128项资源数量守恒断言通过。旧八动作兼容/混合版本同账本由原回归验证。

Pulse Smoke实际加载初态，在t=0读取五基础指标后关闭：advance=0、治疗动作=0；不是新的Pulse治疗实验。14规则静态/算法导入/参数及定义hash检查通过；没有重跑历史疗效实验。

## 独立性与原工程安全

独立.venv为Python3.11.15；核心依赖版本沿用requirements.lock.txt。Pulse仍来自独立`/home/private/pulse-4.3.2-301-runtime`，未修改该软件。运行/业务配置/fixture均来自新工程或明确外部Pulse，不借旧venv。

实际从/tmp用新解释器`-IB scripts/check_independence.py`隔离运行；审计hook拒绝打开原横向树，所有111个可发现子模块来自新src，准入与正式配置检查仍通过。完整日志见validation/independence.json。无源码/业务配置软链接回横向工程，恢复档案不参与运行。旧路径只可能出现在历史来源记录里，不能将其当活跃引用。

原横向目录114127项文件/链接在本轮开始与结束的相对路径、大小、mtime_ns及链接目标摘要一致，见validation/source_protection.json。此为全树元数据核对，不宣称对全部大文件做SHA。所有实际清理写操作限定于科研工程、外部恢复档案及/tmp，原工程未改。

## 科研目录与未完成能力

已新增experiments/scenarios、baselines、ablations、results空目录及记录规范，规定scenario_id/run_id、模型/Agent、资源初态、伤情/方法版本、种子、结果、指标和失败轨迹。没有虚构Baseline、Benchmark、消融或归因实现。

尚存：真实LLM完整计划生成、双Agent反馈/重规划、CompletePlan→Pulse→原十四规则在线闭环、新观测全Runtime激活、临床资源需求确认。Unity由横向项目承担，不是本科研工程验收目标。部分证据依赖仍较重；将来若改准入机制需单独版本化验证，不能本轮静默解除哈希约束。

结论：适合作为后续MAS科研主目录。保留必要兼容债务和外部Pulse依赖的事实，不声称已经完成M3。到此停止。
