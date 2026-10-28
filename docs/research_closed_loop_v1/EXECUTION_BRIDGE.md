# CompletePlan执行桥接与资源回执

实现：`src/core301/research_runtime/bridge.py`。

## 最小范围

`executor_plan`只接受research_fixture / external_hemorrhage / .4和一个control_external_bleeding动作；原CompletePlan校验精确RightLeg、ID唯一、依赖。额外动作（包括合法但本桥接未支持的补液）整组拒绝，不过滤后继续执行。

调用原V2 `CaseRuntime.execute_plan`，由其执行源身份、监测授权、固定180秒时刻、既有设备、幂等和正式协议校验，再调用原 `pulse/v2/treatment_adapter.py` / `proxy_adapter.py`。未改原执行算法、固定参数、M2-A/B/C或医学Prompt。

## 权限链

1. 原 `schedule_complete` 接收完整版本输入，调用原Fixed Provider；后端核验合法计划与snapshot版本、研究能力/权限/地点。
2. coordinator原子确认M2-A预留和onsite任务。allocated=true只在此表示已预留。
3. SharedAuthority.reserve仅检查已有共享预留并关联原executor plan_id，**不再次预留**。
4. SharedAuthority.begin调用coordinator.begin_usage；其核查task/plan身份及treatment_ready_at_s，M2-A再核查资源与动作前序。拒绝则原生_submit不会发生。
5. 原executor提交可信固定payload，并从真实native result回传accepted/rejected/unknown。

## 生命周期

|业务阶段|原实现使用|证据/处理|
|---|---|---|
|RESERVED|manager.reserve，由schedule_complete触发|共享allocation_id、版本1；旧fixture不另扣库存|
|STARTED|coordinator.begin_usage→manager.begin_usage|实际180秒；medic进入IN_USE|
|EXECUTION_ACCEPTED|原_submit明确true→acknowledge→record_execution accepted|execution_events和原native_result；此时不释放|
|EXECUTION_REJECTED|原native记录明确false|record_execution rejected；保守保留占用，不假定未使用|
|EXECUTION_UNKNOWN|提交异常且无确定原生回执|record_execution unknown，QUARANTINED；禁止新ID重试|
|RELEASED|原reconcile确认同源移除及出血率0后，finish→release_usage|本场景无设备/耗材；代理结束后medic研究令牌可复用；本轮保守占用至480秒才释放|
|任务结束|confirm_onsite/end_episode|沿用原coordinator；release_unused只涉及未开始项，不撤销实际执行|

本轮资源最终available=1，reserved/in_use/unavailable/consumed均0。没有一次性物料，所以没有伪造开包或record_consumption事件。耗材桥接和持续设备释放**不在本版执行范围**；既有M2相关守恒/不回滚测试在全量回归中运行，不能称本次原生验证了补液消耗。

end_episode沿用原manager取消剩余预留语义，故终态plan.cancelled=true可与已执行action.FINISHED/accepted并存；它不表示已完成治疗被撤销。`resource_final.json`保留这个真实状态。

## 幂等与异常

CompleteExecutionBridge固定一次request/context绑定；同请求查询原journal不再提交，换ID重试拒绝。Runner实际对同调度请求和同治疗请求各重复调用一次，核实同task/同record及native治疗条数仍为1。已有run目录拒绝复用；不提供进程重启恢复。

未知或失败后 `close_case` 不清账、不释放占用；Pulse close不是回执或设备停止证据。原executor失败时release_unused只能释放RESERVED项，IN_USE/QUARANTINED保留。Mock验证unknown及明确rejected两种路径，不能以取消计划消除不确定性。

资源与Pulse不是可整体回滚事务。当前是单进程可信宿主集成；原native journal持久写入，但M2账本本身不支持崩溃恢复。跨进程事务、泛化多动作顺序执行、持续设备和耗材结束策略未实现。
