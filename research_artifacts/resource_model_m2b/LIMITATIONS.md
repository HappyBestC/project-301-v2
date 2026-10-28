# M2-B 范围与未解决边界

## 已支持的运行范围

同一服务实例、单进程内共享同一个 SharedResourceManager 和 SharedDispatchCoordinator，多线程调度确认及异步 Agent/ETA 决策。全部患者通过 coordinator，不能另建每病例旧 ResourceManager 作为同 run 的并行写者。没有跨进程、跨机器、重启恢复、超时自动释放或进程崩溃事务恢复；历史/幂等缓存仅在内存，未做长期裁剪与性能容量测试。

初始化一次性注册患者和完整旧资产清单，暂不支持运行中增删患者、导入已有运输任务或迁移旧运行。调用方提供单调仿真时间；所有医疗事实应由可信后端记录。旧独立 Demo/病例 Runtime 保留兼容，不自动转为共享模式。只有通过新 coordinator 的集成路径提供本轮的整体确认保证。

## 动作契约兼容

M1/M2-A 目录仍覆盖全部十二正式动作；旧冻结 DispatchInput / TreatmentPlan 只有八动作。本轮没有扩写冻结契约：

| M1 动作 | M2-B 原调度入口 |
|---|---|
| fluid_resuscitation、transfusion、intubation、mechanical_ventilation、needle_decompression、occlusive_dressing、supplemental_oxygen | 可表达，仍须 M2-A 精确研究范围、顺序/目标/互斥校验，不是任意组合准入 |
| chest_tube | 旧枚举有该项，但 M2-A 要求 control_hemothorax_bleeding 前序；完整合法序列不能由现有八动作合同表达，因此此路径不能成功放行 |
| control_external_bleeding、control_internal_bleeding、control_hemothorax_bleeding、remove_from_exposure | ACTION_CONTRACT_UNSUPPORTED；整份计划拒绝，不能删掉前序/暴露动作后调度 |
| inhaled_albuterol | 未开放，拒绝 |

五类复合伤 AB 都包含旧合同不可表达动作，不能宣称已完成全部复合伤的 Agent 调度集成。后续需要单独的版本化完整计划桥接；不允许在当前模块中悄悄改冻结字段。

## 物理身份与医疗证据

医疗 stock/holds 在 M2-A；车、整队和机构接收容量在 coordinator 统一的旧业务表。本轮实现了同一确认边界，没有将床位/车辆强行改造成 M2-A 研究设备令牌。只有明确证明两类物理资产互不重叠，才允许同时占用。`legacy_assets_disjoint=True` 是宿主场景声明，当前没有人员/装备成员清单自动证明它。若 MedicalTeam 包含同一 medic 或其设备池、运输/设施容量在两边重复建模，当前拒绝/不支持统一分配；需要后续 canonical 成员映射，不能虚构“已统一所有实体”。同 ID 重叠已拒绝，异名同物必须由场景证据识别。

team_response 只支持医疗令牌已经位于患者绑定地点的场景；不自动把队伍的移动转成成员/车载设备的地点变更。evacuation 可预留显式目的设施的医疗资源，但必须实际接收后才能使用；不支持途中治疗、移动设备的携带/交接、院际转院或多地点分阶段治疗。机构位置绑定不能由名字/类型推断。ETA 完全沿用旧规则，实际事件仍需配置已确认的 TaskEventPolicy；测试里的 FixturePolicy 不是正式 API04 规则。

所有成功只限 research_fixture 的工程资源调度验证。人员资格、真实器材规格、配血/温控、设施临床条件和监护时间未补证；clinical_design 返回 INDETERMINATE。研究 medic 人数、包/袋数量及 holds 不代表真实医学标准。没有新增医学资源量、临床能力默认值或替代治疗关系。

## 生命周期与接入要求

开始使用必须走 coordinator.begin_usage 以保留调度就绪门槛；直接调用裸 M2-A begin_usage 没有运输就绪信息，不属于集成保障路径。其他医疗事实继续由可信后端调用 M2-A，不能给 LLM 暴露这些操作或自行运行旧单病例扣量逻辑。

cancel/fail/end_episode 对已开始或未知医疗使用采用保守拒绝：先处理真实执行回执和释放证据，再重发终止请求；不会为了取消运输任务而释放不确定医疗资源。此轮没有设计在保留医疗隔离的同时细分释放所有其他运输资产的复杂策略。未知执行不得自动重试，也不由调度错误推导物料未投入。

幂等重放返回历史收据及原版本，不能据此推断资源在当前时刻仍占用；需要新快照。宿主生成不同逻辑事件的唯一 request_id / idempotency_key，不能拿同一个键跨调度、生命周期和裸医疗 API 做不同事情。异步在途重复返回明确未知，调用方等待原响应或重查同键，不启动治疗。模型抛错/取消只发生在资源确认前；此阶段未发送任何治疗。

真实 LLM 的网络/行为表现没有验证，测试通过原 LLM Provider 的 HTTP Mock 证明载荷和解析链路；没有调用付费 API。未进行吞吐基准或大规模故障注入；普通业务拒绝、竞争和预留失败路径已验证。

## M3 前置事项（未开发）

需确定十二动作/完整复合 bundle 的版本化调度合同、实际资源身份及组织成员映射、正式事件策略和后端执行事实来源；明确 future feedback 对 UNKNOWN 与普通不足的不同处理，以及重规划仍须复核全组资源的规则。本轮仅输出稳定冲突与 needs_replanning 提示，没有实现救助 Agent 自动改计划、双 Agent 循环或治疗重试。
