# M3-B 双患者真实执行基础设施

2026-10-19（Asia/Shanghai）。整体状态 **M3B_DUAL_PATIENT_PARTIAL**，独立等待状态 **WAITING_TIME_ADVANCEMENT_VERIFIED**。

正式双患者run `m3b-dual-native-001` 创建两个独立Pulse Worker/Engine，共享同一个run、中央M2账本和Coordinator。两个患者均为相同冻结StandardMale、RightLeg外出血.4。180秒A预留唯一medic，B真实申请返回RESOURCE_IN_USE；A合法控源，181秒确认并释放。B在180→181秒真实推进，资源恢复检查成功，但治疗受到原180秒时点限制而阻断，未用预留取消。两患者各301帧、共同到达480秒，无未解决Allocation。

**未取得双患者治疗PASS**：A治疗1次，B治疗0次；没有为了让B成功而改变时序、编造占用时长或提前释放。A正式评价实际返回NOT_EVALUABLE / MANIFEST_PATIENT_INPUT；B未治疗，动态未治疗分支明确不适用锁定治疗评分，未伪造评价调用。全轮LLM调用为0。

## 入口

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
# 无治疗的双原生实例隔离检查
python -m core301.research_runtime.m3b_smoke
# Fake Worker + 真实M2，绝不作为原生证据
python -m core301.research_runtime.m3b_runner --mode offline_test
# 两个原生Worker，固定计划，无LLM
python -m core301.research_runtime.m3b_runner --mode dual_native
# 只读核验，不重运行Pulse
python -m core301.research_runtime.m3b_verify experiments/results/m3b_dual_patient/m3b-dual-native-001
```

可传 `--run-id`，已有run目录拒绝复用；默认UUID。异常/Unknown的run不可恢复重放，必须保留未知分配证据。两个模式严格分目录和manifest标记。

## 证据入口

- [正式双患者汇总](../../experiments/results/m3b_dual_patient/m3b-dual-native-001/run_summary.json)
- [原生只读核验](validation/native_verify.json)：57文件SHA、双PID、同步时钟、各301帧、资源竞争与等待因果全部通过。
- [隔离Smoke成功](../../experiments/results/m3b_dual_patient/m3b-isolation-002/run_summary.json)：两个原生进程、A改变不影响B、同步180秒、关闭A后B仍能推进。
- [首次Smoke失败](../../experiments/results/m3b_dual_patient/m3b-isolation-001/run_summary.json)：比较JSON字符串的顺序敏感问题；修正为完整JSON语义比较，不忽略状态字段。第二次保存的before/after原文本不同但解析对象全等。
- [离线闭环](../../experiments/results/m3b_dual_patient/m3b-offline-001/run_summary.json)、[离线核验](validation/offline_verify.json)：明确非原生证据。
- [架构](ARCHITECTURE.md)、[全局时钟与时序图](GLOBAL_CLOCK.md)、[资源竞争](RESOURCE_COMPETITION.md)、[执行观测](EXECUTION_AND_OBSERVATION.md)、[测试报告](TEST_REPORT.md)、[限制](LIMITATIONS.md)。

原有838个源码/配置/研究规则文件核验无修改或删除，M3-A及M2核心保持不变。没有进入M3-C。

本轮最终全量非原生回归：**1101 passed、0 failed、26 deselected**（含24项M3-B测试）；见 [测试报告](TEST_REPORT.md)。
