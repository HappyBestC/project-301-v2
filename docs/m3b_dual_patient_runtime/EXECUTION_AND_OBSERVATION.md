# 原生执行、患者身份及观测

运行模式严格分离：offline_test 用显式 FakePulseWorker、真实 M2 代码、固定计划；dual_native 用两个 spawn 原生进程。没有真实 Treatment LLM、第二个 LLM 或外部模型请求。

每个 Worker 命令含 run_id、patient_id、command_id、expected_time_s，回执含独立 worker_pid、实际时刻和原生结果。治疗命令另带 plan_id、action_instance_id、task_id、allocation_ids 的一次性绑定；跨患者绑定拒绝。原 CaseRuntime 检查源、scope、监测、180秒、资源与幂等，原执行桥保留共享/原生ID别名。

Worker超时、死亡、身份错配及异常都作为 uncertain transport，禁止该session继续发送命令。提交不确定时由原CaseRuntime记UNKNOWN，M2隔离占用，停止整个run。不能根据“没有收到accepted”推断动作未发生。close/terminate仅结束进程，不构成资源释放证据。

A于180秒治疗，181秒采用原_reconcile/finish确认控源并释放。B没有治疗回执文件；其时间协议阻断作为全局事件和patient_summary记录，不制造原生拒绝回执。B的短暂恢复预留被明确取消，不是治疗完成。

两个患者分别采集180至480秒每秒观测，预期各301帧。所有行含run、patient、plan、worker PID、全局时间和本机Pulse时间。原公开采样路径包含13项可用字段，其中HR/RR/SpO2/SBP/MAP均保留原单位与缺测语义；诊断用于可信机制验证，不是Agent输入。未宣布十五指标全激活。

181秒B的样本标记WAITING_RESOURCE并保留出血；A的诊断控源确认独立来自A。只有存在180/181两个实际样本及同步轨迹，才可报告真实等待推进。固定相同模型的基线观测可以数值相同，不据此判定状态共享；隔离Smoke的差异操作与治疗后的不同机制轨迹提供独立性证据。

A沿用正式评价入口，原规则/患者SHA/Control条件不改，通常因StandardMale与独立Soldier匹配失败而NOT_EVALUABLE。B未在180秒治疗，动态未治疗支路不适用锁定治疗评分，明确记录NOT_EVALUABLE、evaluator_called=false及原因，不伪造一次180秒治疗评价调用。

只读核验器 m3b_verify 检查精确文件集合与SHA、所有屏障、事件顺序、计划身份、冲突阻塞allocation、新版本/幂等键、两个进程、治疗次数、原生时点、无B伪造回执、资源守恒与等待释放因果。它不重新运行Pulse或评价。
