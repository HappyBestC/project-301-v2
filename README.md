# 301 V2 独立科研工程

科研清理验收：`RESEARCH_PROJECT_CLEANUP_PASS`（2026-10-19）。

**本项目为个人硕士科研工程，不是横向项目的交付版本。** `project-301`负责团队横向开发与Unity联调；本目录`project-301-v2`独立开展LLM-based Multi-Agent Systems研究，两者独立演进。

研究基础包括V2受限伤情与Pulse数字孪生、Treatment Agent决策、Resource Scheduling Agent资源协同、共享资源动态约束，以及锁定治疗效果评价规则。后续研究MAS协作、重规划、协作失败分析与归因、方法对比及消融；本轮没有实现这些新方法。

## 当前事实

十类基础伤情、五类固定复合伤、十二动作、M1/M2-A/B/C已保留。真实Treatment LLM仍输出V1八动作合同；M2-C的完整十二动作计划传递和资源预留已实现，完整计划目前来自研究fixture或显式兼容桥接，尚未接入真实LLM生成和Pulse在线评价闭环。

正式基线：[V2_ENGINEERING_BASELINE](docs/V2_ENGINEERING_BASELINE.md)。本轮清理及验收：[RESEARCH_CLEANUP_REPORT](docs/RESEARCH_CLEANUP_REPORT.md)。研究边界：[RESEARCH_SCOPE](docs/RESEARCH_SCOPE.md)。

## 运行与复核

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
python -m core301.dispatch.shared_resources.demo
python -m core301.dispatch.shared_demo
python -m core301.dispatch.complete_demo
bash scripts/validate.sh
```

三个Demo用明确研究fixture和Mock决策，执行真实共享账本的预留/释放/竞争；无需真实API凭据。validate执行678核心集合、完整单元回归、三个Demo及守恒检查、冻结完整性、Pulse初态观测Smoke和隔离路径检查，不开展新治疗实验。

## 环境

当前独立Python3.11.15虚拟环境在`.venv`；Pulse4.3.2精简运行时独立位于`/home/private/pulse-4.3.2-301-runtime`。`pulse`只链接该外部安装，不链接横向工程。跨机器重建：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python scripts/configure_pulse.py /path/to/compatible/pulse-4.3.2
source scripts/activate.sh
```

需要与冻结证据一致的Pulse构建SHA；同版本不同构建不能自动替换。采用源码检出+editable安装，配置/证据在工程根，不能仅搬运wheel。真实LLM仍需自行设置OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL；`.env.example`不含凭据，本轮未调用真实API。

## 目录与权威

| 目录 | 用途 |
|---|---|
| src/core301 | 保持现有import稳定的研究实现与明确标记的临时兼容层 |
| config | 正式五复合配置；compatibility/v1仅旧合同所需的两份原样YAML，不定义正式V2范围 |
| experiments | 未来scenarios/baselines/ablations/results的空目录和记录规范，无虚构算法或结果 |
| research_artifacts | 原准入逐文件校验的证据、冻结规则/观测和必要研究来源；保留原路径避免破坏校验 |
| research_baseline | 当前科研完整性清单、清理审计；history/migration仅迁移时记录 |
| validation | 本轮最新实际验证结果 |
| docs | 科研范围、架构、状态、路线与兼容债务 |

根目录旧`冻结版/v1`已移除。仍需保留哪些V1代码及其退出条件，详见[LEGACY_DEPENDENCY_AUDIT](docs/LEGACY_DEPENDENCY_AUDIT.md)。[实验记录规范](experiments/README.md)用于未来真实研究。Unity不是本工程路线的验收目标。
