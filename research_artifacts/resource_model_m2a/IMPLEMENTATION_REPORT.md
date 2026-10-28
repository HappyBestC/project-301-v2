# M2-A实现报告

## 1. 实施前核查及复用决定

已完整阅读M1五份指定文档。当前实现与M1的关系是新增共享权威层，保留冻结接口，未让既有Demo/病例Runtime自动切换。

| 已有位置 | 已确认实现 | 共享缺口/本次复用 |
|---|---|---|
| src/core301/dispatch/manager.py:ResourceManager | Facility预留/接收容量、车/队active_task_id、确认到达/接收、终止释放、call_id幂等 | 构造时绑定单患者DispatchInput，_owned_task拒绝其他患者；没有耗材总账、线程锁与共享run库存。本轮保留其功能，不重做转运/设施调度 |
| src/core301/dispatch/models.py | Facility、Ambulance、MedicalTeam、DispatchInput/Proposal/Task | supported_action_types源自V1八动作；未擅自扩展冻结合同 |
| src/core301/dispatch/service.py、providers.py | 决策输入快照、异步ETA及后端再验证 | 未改Prompt或决策，也未接入新反馈循环 |
| src/core301/runtime/v2/resources.py | ResourceAuthority；ResearchResourceFixture以RLock保护stock/holds；reserve/begin/acknowledge/release_unused | run+patient绑定，不能跨伤员；关闭病例会清预留。复用其COSTS与资源职责边界，不复用单病例状态对象 |
| src/core301/runtime/v2/hemothorax_resources.py | 血胸控源与胸管COSTS、显式授权和消耗 | 通过V2.1统一COSTS直接复用，无新医学物料推断 |
| src/core301/runtime/v2_1/resources.py | 合并12动作COSTS、研究暴露凭据、整序列stock累计/holds最大值 | HostResources被deep-copy进单病例；不共享。新Catalog直接导入此COSTS，数量/权限不维护第二份手写表 |
| src/core301/runtime/v2_1/contracts.py:HostResources | run_id/patient_id/stock/holds/capabilities/permissions及路径条件 | 未将其副本作为新服务库存，未改契约 |
| src/core301/contracts/context.py:ResourceState | 旧8个计数字段 | 无资源ID/位置/单位/占用记录；本轮不伪造有损投影为完整权威 |
| src/core301/contracts/v2/treatment.py | 互斥、顺序、插管通气成对、目标字段 | Catalog直接调用TreatmentPlan校验，不另写一份通用动作冲突表 |
| src/core301/runtime/v2_1/registry.py | config哈希检查、五个复合Profile | 复用patterns()及其哈希校验；仅接受精确AB序列 |
| research_artifacts/v2_restricted_engineering_baseline_v1.0/TEN_INJURY_CONFIGURATIONS.json | 十类冻结伤情/动作/严重度/位置 | 新资源计划必须引用一个既有scope；不按12动作任意拼接 |
| tests/test_dispatch.py、tests/v2/test_runtime.py等 | 旧设施/车/队、合同和单病例fixture验证 | 选择相关独立单元回归，未调用native集成测试 |

医学未知项保留。M1拟议实体中M2-A实现Resource、TreatmentRequirement及分配/事件必要字段；Location是按ID引用的当前能力/权限/研究环境条件快照，不是另起一套完整医院、团队或运输系统。旧设施床位/救护车生命周期仍由旧模块负责，尚未并入新账本。

## 2. 新增文件

| 文件 | 职责 |
|---|---|
| src/core301/dispatch/shared_resources/models.py | 严格Pydantic输入、三值Result、稳定Conflict字段 |
| catalog.py | 从已有COSTS生成12个TreatmentRequirement，复用既有范围和约束校验 |
| manager.py | 按run的共享状态、原子事务、分配记录、幂等与事件 |
| fixtures.py | 显式研究场景构造器；仅使用调用方提供的数量 |
| demo.py | 两伤员竞争、占用、实际消耗、释放和重申请示例 |
| tests/shared_resources/test_manager.py | 并发、事务、生命周期、未知、范围、数量守恒测试 |

既有文件零修改；本轮新代码只位于独立子包，不继承旧ResourceManager以免引入其单患者所有权与转运流程。没有新增依赖或数据库。

## 3. 原子性与数量

一个SharedResourceManager持有run_id→RunState。create_run禁止同一实例重复初始化run，避免覆盖活跃库存；实例由后端创建并共享，患者只提供关联ID。所有读写使用同一个RLock，支持同进程多线程；不同run数据独立但当前锁串行化全部run写入，优先简单可靠。

变更先在锁内检查幂等/版本/仿真时间，再深复制状态执行，数量守恒验证成功后一次替换。任何业务失败不提交库存、计划或allocation的部分变化。结果与事件缓存会记录拒绝，但不增加资源state_version。成功操作（包括执行事实/位置/能力变更）增加版本；所有对外快照及事件为独立副本。

计数采用研究资源的非负严格整数，拒绝bool、浮点数量、NaN、Infinity和数值字符串。stock单位为bag/kit，medic为person，evacuation_team为team，其余研究holds为device令牌。鼻导管/氧源的holds分类只是旧fixture计账，不代表现实复用规范；不自动将500 mL或425 L转成连续用量。

`total_qty = initial_total + received_qty - consumed_qty - lost_qty`。

`total_qty = available_qty + reserved_qty + in_use_qty + unavailable_qty`。

total与各分区从资源事实/Allocation计算，不接受调用者直接赋值。unknown初量保持null且不能预留。views只引用canonical resource_id，不另建数量。received/lost必须有显式数量、原因、回执；lose仅允许移除未分配可用量，不能越过现存占用直接销账。

## 4. 可行性与顺序

evaluate_requirements只读，不写事件、幂等缓存或扣量。SATISFIED仅说明明确研究scope中的资源约束已满足，不授权临床或Pulse执行。临床模式固定返回QUALIFICATION_UNVERIFIED/INDETERMINATE；数量、地点、能力或权限未知返回INDETERMINATE；已知不足、故障、错误地点/动作组合返回UNSATISFIED。

同一计划stock按动作累加。holds沿用单序列最大量，但新增严格串行使用条件：前序动作必须record_execution(accepted)且release_usage有结束使用证据，下一动作才可begin。同一资源的后续动作仍有预留需求时，结束当前使用会回到RESERVED而非变成跨患者可用。跨计划绝不取最大值合并占用。

同一patient仅允许一个未结束计划。旧计划存在unknown或未释放状态时，换plan_id/action_instance_id也不能重新申请绕过隔离。已结束/取消的plan_id不重用，action_instance_id在run内全局唯一。

全部12个动作来自现有COSTS；scope_id是十类基础伤情injury_type或五类复合pattern_id；severity必须符合基础固定值，复合配置使用固定组件且severity=null。动作target必须为冻结Left/RightLeg/Spleen；气道成对、支持互斥等直接复用旧合同。inhaled_albuterol无资源需求且拒绝预留。

## 5. 接口与调用约定

共同Request字段：run_id、patient_id、plan_id、request_id、idempotency_key、action_instance_id（整计划/资源事件用null）、at_s、expected_state_version。后端提供单调不减的run仿真秒；没有墙上时钟、自动超时、到期释放或后台任务。

| 方法 | 关键参数 | 语义 |
|---|---|---|
| create_run | run_id, Resource[], Location[], views | 后端一次性注册完整的显式研究场景 |
| get_snapshot | run_id, view可选 | 返回共享库存、位置/能力、分配、计划及版本 |
| evaluate_requirements | Request, Plan | 只读三值检查；旧version返回STALE_SNAPSHOT |
| reserve | Request, Plan | 全组选择/预留；冲突时库存完全不变 |
| begin_usage | Request(action实例) | 复查位置/故障/能力/权限及前序状态；占用资源，不消耗物料 |
| record_consumption | Request, amounts={allocation_id:整数}, receipt_ref | 实际开包/投入等资源事实；逐项核对所有权、余量后原子扣量 |
| record_execution | Request, Execution(status,receipt_ref) | accepted/rejected/unknown；不扣耗材，也不释放设备 |
| release_unused | Request(action=null), reason | 取消剩余计划、释放未开始预留；已开始/耗用/隔离保持 |
| release_usage | Request, ReleaseEvidence, returned_unused_consumables | 对已知执行的动作，确认停止/脱离当前资源使用/可复用后结束占用 |
| record_resource_change | Request, ResourceChange | fault/unavailable/restore/move/receive/lose；返回受影响allocation IDs |
| record_location_change | Request, Location, receipt_ref | 后端记录能力/权限和研究环境条件变更，推进版本 |
| get_events | run_id | 返回脱离内部状态的事件列表，包含请求、事实、结果、原因 |

ReleaseEvidence的stopped/detached/cleared_for_reuse针对被分配的人员/设备使用；它不生成拔管等临床操作，也不解除原生插管。已投入耗材保持CONSUMED；仍未投入的耗材只有显式`returned_unused_consumables=True`且有回执才能归还。不能通过“动作完成”推断全部物料实际使用。

新包模型支持model_validate(Python dict)与model_validate_json(JSON)；由于strict=True，Python输入的actions用tuple、能力/权限用frozenset，JSON入口由各模型的model_validate_json解码。未知schema字段拒绝。对象经model_copy篡改的非法值在公共入口也会重新验证。

幂等范围为run内全操作共享的idempotency_key。指纹包含operation、完整Request及payload；同键同内容返回首次结果（包括首次失败和旧state_version），不同内容返回IDEMPOTENCY_CONFLICT。新的时刻/版本/请求ID也是不同内容，处理STALE_SNAPSHOT后须读取新快照并用新键发起新请求。动作已开始/结束时，即使用新键也不能再次begin；耗材全部消费后也不能再次消费。调用方须以同一逻辑资源事件稳定复用原键，不能把同一补给事实伪装成多个新事件。

对写接口，SATISFIED表示该资源事实已成功记录；例如record_execution(unknown)成功记录隔离事实，不表示治疗状态已知。后续可行性/释放仍返回EXECUTION_UNCERTAIN。

Result统一含schema_version/run_id/patient_id/plan_id/request_id/state_version/outcome/conflicts/allocation_ids/affected_allocation_ids。Conflict含动作/需求/资源标识、required_qty/available_qty/unit、blocking_allocation_ids、version、detail及来源。非数量冲突的数量字段为null。详细类型见models.py；结构非法、run不存在等调用错误抛ValueError/ValidationError，正常资源不足等业务冲突返回Result。

## 6. 异常与持续使用

- 开始前取消：未用资源返还；消耗量不变。
- 开始后拒绝/失败：已投入不返还，未投入物料需明确未用证明；设备仍占用到release_usage。
- unknown回执：活动分配进入QUARANTINED，未投入剩余量计unavailable；已消耗从total移除。release_unused不能释放这些资源；begin不能重放。
- 后端取得可靠回执后，可将unknown补记accepted/rejected；保持隔离，直到显式释放。已知final回执不能再覆盖。
- 故障把活动使用分配隔离；未开始预留仍保留占有声明但begin拒绝。未分配余量转不可用。restore只恢复设备可工作标记，不释放隔离分配。
- move改变位置和版本但不自动完成任务或释放资源。先前reserve成功不保证begin成功。
- begin复查失败后保留预留，返回原因，由后端调用release_unused明确取消。本项是对M1“终止未开始组”的最小调整：避免一个失败读检查隐式撤销宿主计划，未修改旧Runtime行为。

## 7. 与后续Agent接口的边界

Result及版本化Request可作为M2-B的确定性后端接口，Agent只能提交建议，不能写账本。尚未将新快照投影到旧8字段，也未把HostResources变成共享状态，更未将旧ResourceManager与新服务同时用于同一资产。下一阶段须决定唯一权威、车辆/设施容量桥接与Plan/bundle转换；本轮没有执行这些集成。
