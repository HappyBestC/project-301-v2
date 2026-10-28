# 真实资源竞争与恢复检查

一次 run 只创建一个 SharedResourceManager 和一个 SharedDispatchCoordinator，research_scene({'medic':1}) 产生唯一 canonical medic 资源池。两个患者一起 register_run，各自唯一 patient_id/plan_id/action_instance_id。优先顺序显式固定为 A→B；schedule(label, request) 是未来策略可调用的窄接口，本轮无 Agent/优先级学习。

两个计划均为正式 CompletePlan，RightLeg .4 的单动作 control_external_bleeding。FixedDispatchProvider 提出 onsite，无队伍、车辆或机构选择。资源需求来自正式 Catalog，不复制到 Worker。

B 初次申请真实调用 schedule_complete，并读取 A 预留后的版本，反馈 RESOURCE_IN_USE、required=1、available=0、resource_id=medic、blocking_allocation_ids=A分配。它不是宿主预构造冲突，也不是 stale 视图造成的假竞争。

| 顺序 | 资源状态与事实 |
|---|---|
| 初始 | available=1 |
| A预留 | reserved=1，available=0 |
| B申请 | UNSATISFIED；无B部分预留，保留原冲突 |
| A开始 | in_use=1；对应任务已ready |
| A原生接受 | 仍占用，accepted不释放 |
| 181秒确认 | 原 CaseRuntime 提供 source_control_confirmed，原 SharedAuthority.finish 提供 ReleaseEvidence |
| A释放 | available=1；无设备、无耗材 |
| B被唤醒 | 记录释放事件序号，读取新state_version，使用新request/idempotency key |
| B恢复申请 | 可预留，但这不授权181秒治疗 |
| B时窗拒绝 | UNVALIDATED_TIMING；不提交Pulse，原coordinator.cancel取消未使用预留 |
| 终态 | available=1、reserved=0、in_use=0，无无法解释的占用 |

旧失败幂等键仍返回原失败，不能期待自动变成功。无资源变化时不轮询重复申请。Unknown 不换plan_id重新执行，原manager隔离占用；实验异常时导出 unresolved_allocations，不强行释放。

全局事件为观察与编排记录，不另建医疗状态机：正式状态仍来自 DispatchTask、M2 Allocation/PlanState 和原执行 journal。onsite 不伪造运输 TaskEvent。
