# 301 M2-C：十二动作完整计划与共享调度

2026-10-19。新增版本化完整计划及调度输入，复用同一个 SharedDispatchCoordinator / SharedResourceManager。旧TreatmentPlan、DispatchInput、Proposal、TaskEvent与冻结研究配置均保持原文件不变。没有开发M3。

- `301.treatment.complete.1` → `core301.dispatch.complete_contracts.CompletePlan`。
- `301.dispatch.complete.1` → `CompleteDispatchInput`，含完整计划及十二动作能力列表。
- 结果保持 `301.dispatch.shared.1`，医疗账本保持 `301.resource.m2a.1`。

```text
正式配置构建的完整研究计划（或显式无损旧计划桥接）
 → CompletePlan：校验完整scope、目标、顺序、串行依赖
 → CompleteDispatchInput：保持全计划，不降为旧八动作
 → 原dispatch.service / 原Fixed或LLM Provider
 → 原五字段DispatchProposal
 → 原SharedDispatchCoordinator整体确认
 → 原M2-A完整需求检查、原子reserve
 → allocated=true / 结构化冲突或INDETERMINATE
```

完整动作合同可表达，不表示救助LLM已能生成或临床/Pulse已验证。真实救助Provider仍为V1；本轮的完整输入来自明确的研究fixture。

## 运行

在项目根目录：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.complete_demo

PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/complete_dispatch -o cache_dir=/tmp/301-m2c-tests
```

Demo输入为正式胸部穿透性复合AB：`occlusive_dressing → control_hemothorax_bleeding → chest_tube`。通过现有Agent入口、M2-A和M2-B确认A的真实预留，再对B返回真实冲突。输出同时记录输入完整计划、Provider实际接收计划、前后账本和分配/冲突，不仅做Pydantic解析。

最小调用示例（整个Demo为可直接运行版本）：

```python
from core301.dispatch.complete_demo import research_plan, research_input
# 这是显式研究fixture，不是救助Agent生成。
plan = research_plan('penetrating_thoracic_composite_v2', 'A', 'run')
source = research_input(plan)
# 后端先创建一个SharedResourceManager的run，注册统一资源/Location，
# 并用coordinator.register_run(..., inputs=[source], ...)绑定位置与资产。
# 然后使用M2-A Request的版本、时间、关联ID：
# result = await coordinator.schedule_complete(request, plan, provider, eta_provider)
```

JSON入口可使用 `CompletePlan.model_validate_json` 和 `CompleteDispatchInput.model_validate_json`；Python字典按既有M2-A strict约定，actions/depends_on用tuple。无版本旧DispatchInput仍走原行为；新输入必须提供精确版本。额外字段/原生剂量参数不会被吞掉。

文档：[真实支持矩阵](CONTRACT_AUDIT.md)、[实现与兼容](BRIDGE_IMPLEMENTATION.md)、[测试报告](TEST_REPORT.md)、[边界](LIMITATIONS.md)。原始Demo输出见 [demo_output.jsonl](demo_output.jsonl)。
