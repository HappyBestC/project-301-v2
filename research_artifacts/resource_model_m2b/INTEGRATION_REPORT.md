# M2-B 集成报告

## 现状核查

依据 M1 五份设计文件、M2-A 实现/测试/局限报告和当前代码核查，结论如下。

| 模块 | 既有行为 | 本轮处理 |
|---|---|---|
| dispatch/service.py、providers.py | Agent 从 DispatchInput 的 facilities / ambulances / medical_teams 得到候选；异步查询 ETA；返回五字段 proposal | 保留原入口与 ETA 校验；增加可选 shared_resources 只读投影和显式 Provider 支持 |
| dispatch/manager.py:ResourceManager | 单患者入口；accept 最终创建任务并占车/队或预留机构容量；event / admission / terminate / end_episode 负责阶段与释放 | 不删除、不改写；在 coordinator 的副本上复用全部方法，run 级统一发布 |
| dispatch/models.py、contracts/treatment.py | 冻结 V1 八动作；TaskEvent、坐标和机构字段已经稳定 | 零修改，不能直接扩成 M1 十二动作 |
| dispatch/eta.py、eta_validation.py、events.py | ETA 只预测；需要有效查询证据；实际到达依 TaskEvent 和显式事件策略；设施接收另行确认 | 零修改，原路径照常执行；没有用 ETA 代替到达 |
| dispatch/shared_resources/manager.py | M2-A 同 run 权威 stock/holds、三值校验、全组预留、消费/隔离/释放、版本、线程锁 | 直接使用原账本；只新增同步 serialized 上下文，供确认过程共用锁 |
| runtime/v2/resources.py:ResourceAuthority 及 research fixture | 单病例资源接口；绑定患者，旧投入/释放语义 | 不接入，不复制其库存，不让它与共享资源重复扣量 |
| runtime/v2_1/HostResources 及 COSTS | 单病例 HostResources 副本；十二动作研究数量/权限和固定范围 | M2-A Catalog 仍复用 COSTS；本轮不另写医学资源规则 |
| contracts/context.py:ResourceState | 旧八计数字段，无唯一设备身份、版本、分配实例 | 不作为共享权威，也不将详细资源强行压成该结构 |
| agent/ | 救助 Agent 的规划、配置、Prompt | 完全不修改；本轮不形成反馈循环 |

旧 ResourceManager 不维护 ventilator、袋/包等 M2-A 医疗库存。潜在重叠是“旧整队”与“新版人员/撤离团队令牌”、车载设备以及床位/能力槽位的真实身份；仅名称不同不能证明独立。因此本轮没有宣称将所有实体搬进同一通用账表。

## 源码修改清单

既有文件仅修改三份：

1. `src/core301/dispatch/shared_resources/manager.py`：新增 `serialized(run_id)`，所有既有操作与数值语义不变。
2. `src/core301/dispatch/service.py`：可选 `shared_resources` 参数；向 Provider 传独立副本。未实现新方法的旧 Provider 在共享调用中明确失败，不回退。无该参数的原调用行为保持不变。
3. `src/core301/dispatch/providers.py`：Fixed / LLM Provider 增加 `decide_dispatch_with_resources`；复用原输出解析/ETA 工具逻辑；LLM 仅在共享调用追加专用说明和 JSON sidecar。

新增源码：

- `src/core301/dispatch/shared_integration.py`：run 级 coordinator、结构化 DispatchOutcome、投影、确认、幂等、生命周期和历史查询。
- `src/core301/dispatch/shared_demo.py`：通过原 Agent 服务入口的双伤员研究 Demo。
- `src/core301/dispatch/prompts/shared_resources.md`：仅共享调用生效，明确替代旧 Prompt 的“用品数量不参与判断”限定；不改变治疗计划或 proposal 格式。原 dispatch_decision.md 及全部救助 Prompt 保持原字节。
- `tests/shared_dispatch/test_integration.py`：离线集成测试，含线程竞争、异步在途重复、HTTP Mock LLM 和原事件生命周期。

没有新依赖、数据库、原生仿真或网络请求。

## 唯一权威与确认边界

`SharedResourceManager` 拥有全部医疗数量、allocation、占用/实际消耗/故障/隔离/释放。`SharedDispatchCoordinator` 拥有集成 run 的唯一车、队、容量、任务表及各患者位置/生命周期；旧 ResourceManager 是其内部状态转换器。每次转换从这些统一表生成副本，不以某患者保留的旧资产快照作为库存来源。外部只得到脱离内部对象的 DispatchInput、投影或收据。

后端在 register_run 一次性提供同 run 的初始患者输入、患者/机构 location_id 映射。所有患者必须引用完全一致的初始旧资产状态；已有运输任务暂不导入；重复注册拒绝。与 M2-A 重名的 canonical asset ID 拒绝。team_response/evacuation 另需后端明确 `legacy_assets_disjoint=True`，表示旧整队/车辆/接收容量与医疗令牌是不同实际资产，不是 LLM 可声明的字段；无法核实为独立时返回 CONSTRAINT_UNKNOWN / INDETERMINATE。当前没有成员/装备清单可自动验证真实身份，边界在 LIMITATIONS。

确认时持有与 M2-A 相同的 RLock，按以下顺序：

1. 核对决策开始读取的医疗版本、旧状态版本；旧快照不得绕过校验。
2. 核对整份原 TreatmentPlan、患者身份、动作契约、显式治疗地点及所有权。
3. M2-A evaluate_requirements 返回 SATISFIED 后，在隔离副本调用原 accept，核对旧车/队/容量/能力，生成尚未发布的任务。
4. 调用 M2-A reserve。失败则抛弃旧副本，旧预留从未发布，不需要补偿撤销。
5. 仅当 reserve 真正成功，在同一锁内以纯赋值发布已校验旧状态。此后无 await、外部回调或校验操作。返回 allocated=true 和真实 allocation_ids / task。

这是一进程内的同步提交边界，不是 Pulse 与资源的可回滚事务。进程崩溃/MemoryError不提供恢复保证。网络模型/ETA等待期间不持锁。不同 run 的数据隔离，但共用 M2-A 全局实例锁，暂不追求大规模并行吞吐。

## 输入、结果与幂等

Agent 仍接收原 DispatchInput 及五字段输出要求。新增只读 `301.dispatch.resource_view.1` sidecar 包含资源 ID/类型/单位/位置/数量分区/可工作状态、医疗和旧状态版本、Location 能力/权限、当前动作研究需求及来源、地点绑定和临床条件未知标记。没有 manager、修改方法、原始生理状态、隐藏 severity 或评价结果。LLM 不能写库存或调整 TreatmentPlan；scope/severity 只在后端 M2-A Plan 中验证。

`SharedDispatchCoordinator.schedule(Request, Plan, provider, eta_provider)` 使用 M2-A Request 全部关联字段。Plan 必须与该患者注册的原 TreatmentPlan 逐动作、顺序、目标一致，后端补充 scope/实例 ID/地点，不从 LLM 推断。`allocated=true` 唯一含义是本次整组调度实际确认；提案成功、只读可行性成功或 ETA 可达均不等于已分配。

`DispatchOutcome` 字段：schema_version、allocated、resource_result（原 M2-A Result）、legacy_state_version、task（可空）、needs_replanning。医疗冲突完整保留 requirement/resource ID、需求/可用量、单位、阻塞 allocation_id、版本和证据。旧错误保留可解释 detail，未建立跨账本的伪 allocation；非数量失败对应字段为空。旧 ETA/合同错误保留既有原因码；新增 ACTION_CONTRACT_UNSUPPORTED、PLAN_MISMATCH、REQUEST_IN_PROGRESS 等明确适配边界。needs_replanning 只是供将来调用方使用的提示，不触发循环；未知执行返回 false，避免诱导直接重提治疗。

schedule 与 lifecycle 共享调度层幂等键约束。同键同请求重放原收据（包括原版本和失败）；不同内容拒绝。已提交 request_id 换新幂等键也拒绝，避免旧 accept 的 call_id 缓存与新医疗预留错配。同键请求仍等待 Agent 时返回 INDETERMINATE / REQUEST_IN_PROGRESS，不启动第二次决策。新时刻/版本必须使用新逻辑请求；未知执行不能靠新 plan ID 绕过 M2-A 隔离。取消异步决策尚未进入确认时不会有资源投入，原 request_id 已占用，重新决策应使用新 request_id/key。

M2-A 医疗事实事件仍使用其原全操作幂等语义；宿主须为调度、生命周期、医疗事实分配全 run 唯一的逻辑事件键，不将一个键跨 API 层用于不同操作。`get_history(run_id)` 返回调度及生命周期请求/收据的独立副本；`medical.get_events(run_id)` 返回医疗事实事件。两者为内存记录，不是持久审计平台。

## 生命周期对接

- `begin_usage(Request(action_instance_id), task_id)`：先核对所属任务，onsite 已分配可开始；team 必须真实到患者；evacuation 必须实际到站并经原 confirm_facility_admission。然后调用 M2-A begin_usage 重查故障、地点、权限、前序等。ETA 不能使其就绪。
- `lifecycle(Request(action_instance_id=None), task_id, operation, ...)`：支持 event、admit、confirm_onsite、cancel、fail、end_episode。复用原 TaskEvent/ETA后到达/设施接收/车队释放规则。event 必须配置已有显式事件策略；无策略不猜测到达。
- cancel/fail/end_episode 在有 STARTED / QUARANTINED 医疗动作或 IN_USE / QUARANTINED allocation 时拒绝并保留旧资产；先由实际回执和停止依据处理医疗使用，再结束旧任务。未开始预留通过 M2-A release_unused 安全取消，两侧成功才发布旧释放。
- 正常 confirm_onsite/admit 只确认旧调度阶段，不声称治疗成功、不释放医疗设备。设施接收占位到 end_episode；救护车在接收时按旧语义释放。
- 实际开包用 M2-A record_consumption；执行 accepted/rejected/unknown 用 record_execution；停止/脱离/清理证据用 release_usage。accepted 从不自动消耗或释放。已消耗不回滚；UNKNOWN 保留隔离，不重试治疗。
- 所有时间来自宿主仿真秒，无墙钟到期或自动释放。医疗版本与旧状态版本分别报告；只变旧生命周期不伪造医疗库存变化。
