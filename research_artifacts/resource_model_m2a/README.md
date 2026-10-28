# 301 M2-A：共享医疗资源状态管理器

已实现独立可运行版本。入口：[SharedResourceManager](../../src/core301/dispatch/shared_resources/manager.py)，契约版本 `301.resource.m2a.1`。同一后端服务内每个run只有一份库存，所有patient调用共享该服务；不同run隔离。当前为显式research_fixture工程实现，不是临床能力认证，也不授权Pulse执行。

## 运行

在项目根目录执行，使用已有Python环境，无需安装新依赖：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.shared_resources.demo
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/shared_resources -o cache_dir=/tmp/301-m2a-pytest
```

[demo.py](../../src/core301/dispatch/shared_resources/demo.py)是完整最小调用示例。它创建两名模拟伤员、两份研究气道包和一台呼吸机，依次执行只读检查、A整组预留、B冲突、A开始使用/确认开包/接收回执、A停止并释放、B重新申请和取消。所有输出来自管理器真实快照和操作结果，运行保存见[demo_output.jsonl](demo_output.jsonl)。Demo中的回执是显式模拟资源事实，不运行Pulse或Unity。

基本初始化示例：

```python
from core301.dispatch.shared_resources import SharedResourceManager
from core301.dispatch.shared_resources.fixtures import research_scene

manager = SharedResourceManager()  # 在后端创建一次，注入全部患者调用方
resources, locations = research_scene({
    "medic": 2, "airway_kit": 2, "ventilator": 1,
})
manager.create_run("RUN-1", resources, locations,
                   views={"team": ["ventilator"], "facility": ["ventilator"]})
snapshot = manager.get_snapshot("RUN-1")
```

此场景数量是工程示例。`research_scene`只在显式调用时赋予研究能力/权限与路径凭据，不被运行时自动调用。缺少的资源类型表示这个显式封闭场景未配置该资源；未知数量必须填写`None`，不能用0代替。真实临床需求用`scope_kind="clinical_design"`，当前返回INDETERMINATE。

## 阅读入口

- [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)：旧代码核查、复用方式、接口与状态语义。
- [TEST_REPORT.md](TEST_REPORT.md)：实际测试命令、结果与覆盖。
- [LIMITATIONS.md](LIMITATIONS.md)：并发范围、持久化、医学与后续对接边界。
- [SOURCE_PROTECTION.json](SOURCE_PROTECTION.json)：1130个既有源码/配置/M1及规则文件的前后哈希核对。

八个M1接口均已提供；另有独立的`record_consumption`与`record_location_change`，避免将接受治疗回执当作消耗事实，或让能力/权限变更绕开版本检查。结构化业务失败使用Result；非法输入结构由Pydantic拒绝。

本轮没有改Agent、旧运行入口、伤情配置或疗效规则；没有双Agent反馈循环、新Pulse实验或Unity接入。
