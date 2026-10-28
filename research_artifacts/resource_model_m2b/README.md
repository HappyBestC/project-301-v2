# 301 M2-B：共享资源与现有调度 Agent 集成

2026-10-19。已实现可运行的最小集成：同一 run 的多伤员通过既有 `decide_dispatch` 服务和 Provider 接口提出建议，由后端同时确认旧调度资产和 M2-A 医疗资源。没有新增 Agent、自动重规划或 Pulse 执行。

入口：`src/core301/dispatch/shared_integration.py:SharedDispatchCoordinator`。结果版本 `301.dispatch.shared.1`；医疗结果继续使用 `301.resource.m2a.1`。冻结的 DispatchInput / DispatchProposal / DispatchTask / TaskEvent 未修改。

```text
原 DispatchInput + 后端提供的只读 shared_resources 投影
  → 原资源调度 service / FixedDispatchProvider 或 LLMDispatchProvider
  → 原 DispatchProposal（五字段，不能改治疗计划）
  → 重新核查两个状态版本、地点、能力和 M2-A 需求
  → 在副本上执行原 ResourceManager.accept
  → M2-A.reserve 原子预留成功
  → 同一锁内发布旧车/队/容量状态和 DispatchTask
  → DispatchOutcome（成功分配或结构化失败/未知）
```

医疗资源唯一写者为 M2-A。旧 ResourceManager 继续提供车、队、容量、ETA 后事件和任务生命周期规则，但在集成路径中仅作为副本状态转换器，权威旧状态集中于 coordinator 的 run 记录。不把 medic 令牌自动当作 MedicalTeam 成员；不能证明资产不重叠时，team_response/evacuation 返回 INDETERMINATE。

## 运行

在项目根目录，使用现有虚拟环境，无需安装依赖：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.shared_demo

PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/shared_dispatch tests/shared_resources -o cache_dir=/tmp/301-m2b-pytest
```

Demo 通过原 `dispatch.service.decide_dispatch` → `FixedDispatchProvider` 发起 A/B 请求，打印真实结果、allocation 与资源版本：A 预留、B 冲突、A 实际投入气道包、占用通气设备、依据明确事件释放、B 再申请成功、B 取消。没有调用模型或 Pulse。原始输出在 [demo_output.jsonl](demo_output.jsonl)。

最小 Python 调用（明确为研究 fixture）：

```python
import asyncio
from core301.dispatch.shared_integration import SharedDispatchCoordinator
from core301.dispatch.shared_resources import SharedResourceManager, Request
from core301.dispatch.shared_resources.fixtures import research_scene
from core301.dispatch.shared_demo import fixture_input, fixture_plan, fixture_provider
from core301.dispatch.demo import demo_eta

medical = SharedResourceManager()
stock, locations = research_scene({'medic': 2, 'airway_kit': 2, 'ventilator': 1})
medical.create_run('run', stock, locations)
dispatch = SharedDispatchCoordinator(medical)
dispatch.register_run('run', [fixture_input(p, 'run') for p in ('A', 'B')],
                      at_s=45., patient_locations={'A': 'scene', 'B': 'scene'})
request = Request(run_id='run', patient_id='A', plan_id='plan-A',
    request_id='request-A', idempotency_key='schedule-A', action_instance_id=None,
    at_s=46., expected_state_version=medical.get_snapshot('run')['state_version'])
result = asyncio.run(dispatch.schedule(request, fixture_plan('A'),
                                       fixture_provider('A'), demo_eta()))
assert result.allocated
print(result.model_dump_json(indent=2))
```

部署范围：一个进程内共享同一个 medical 与 coordinator 实例，可多线程；没有跨进程/重启恢复。业务时间全部为调用方的仿真秒。旧独立 Demo/Runtime 保留原样，不能同时作为集成 run 的另一资源写入口。

完整修改与所有权说明见 [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md)，真实测试见 [TEST_REPORT.md](TEST_REPORT.md)，动作契约限制与 M3 前置条件见 [LIMITATIONS.md](LIMITATIONS.md)。
