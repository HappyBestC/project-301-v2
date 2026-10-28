# M2-C 合同桥接实现

## 新合同复用范围

新增 `src/core301/dispatch/complete_contracts.py`，不修改任何冻结合同原文件。

`CompleteAction` 继承 M2-A Action：保留 action_instance_id、action_type、side、compartment，仅将类型收紧为十二正式动作，并增加必填 depends_on。`CompletePlan` 继承 M2-A Plan：保留patient_id/plan_id/scope_kind/scope_id/severity/location_id/actions，增加必填schema_version/run_id、execution_policy=m2a_serial_execution、parameter_policy=fixed_profile_no_overrides。没有新资源状态或成本表。

每个动作的 depends_on 是原M2-A已实行的串行链：第一个为空，其后依赖紧邻前序ID。它表示资源执行必须等前序accepted且释放使用，不把工程串行规则伪称为新的临床依赖。声明与顺序不一致即DEPENDENCY_UNMET。真正动作/目标/配对/控源前置/互斥/研究范围继续调用原Catalog.validate_scope和既有V2校验器；五类复合伤必须精确AB，不能换成BA/子集或临时组合。

业务合同已有的参数是side/compartment，全部保留。剂量、输注速度、通气设置、环境气体比例原本由固定profile执行器定义，不是旧TreatmentPlan/HostResources允许用户覆盖的字段。新合同显式记录fixed_profile_no_overrides及原scope，不复制一份native参数表；输入额外参数（包括空parameters对象）会拒绝，不会静默丢弃或填默认剂量。原生参数依旧归既有执行器所有，本轮没有生成执行载荷。

`CompleteDispatchInput` 继承旧DispatchInput，显式版本化并覆盖treatment_plan类型。Facility、MedicalTeam使用各自子类，仅扩展supported_action_types到十二正式动作；容量、位置、占用、唯一ID、跨run/患者引用等旧校验全部继承。Ambulance、DispatchProposal、DispatchTask、TaskEvent不改。不能只替换plan而遗漏设施/小队的八动作约束。

## 桥接与版本识别

- `decode_dispatch_input`：无schema_version是原V1输入；精确301.dispatch.complete.1是新版；其他版本拒绝，不猜版本。深层输入重新验证，通过model_dump/validate生成独立树。
- `from_legacy_plan`：先校验原TreatmentPlan，由可信后端显式提供run/plan/稳定动作ID/范围/严重度/地点；动作数量必须与ID数一致，按原序复制类型和目标。不会推断scope或自动配对插管。原V1合法不代表符合M2-A研究scope；不符合仍拒绝，新桥接不改变原V1路径行为。
- `from_resource_plan`：已完整给定的M2-A Plan变成新版，仅显式标记已有串行执行策略，随后验证范围。无排序、补动作或过滤未知动作。
- `to_resource_plan`：完整计划映射到原M2-A字段，动作ID/数量/类型/顺序/side/compartment/范围/严重度/地点全部相同。新增版本/run在外层对照验证，depends_on严格等价于原M2-A串行执行门槛。完整原计划仍保存在DispatchInput，Agent与后续调用得到的是完整原对象副本，并不把这个内部需求视图当成降级的业务计划。
- `to_legacy_plan`：明确LOSSY_CONVERSION拒绝。即使动作都属于V1，也不能声称将实例ID、依赖、范围和策略无损放进无相应字段的V1结构。旧V1可继续原路径，也可显式向上桥接；不提供有损向下转换。

Python strict模型遵循M2-A tuple等类型约定。JSON用model_validate_json解析；导出Schema见complete_plan.schema.json、complete_dispatch.schema.json。JSON Schema描述字段范围；完整顺序与scope规则还须执行后端validator，不把单纯Schema通过当成业务准入。

## 最小修改点

| 既有源码文件 | 修改及原因 |
|---|---|
| dispatch/shared_integration.py | register_run识别新版输入；同run旧/新资产按完整字段一致性比较；为原ResourceManager注入正确模型/validator；新增schedule_complete验证版本、完整计划身份和不可改写；随后仍调用原schedule→_confirm→M2-A.reserve。新输入支持十二能力，旧输入保留原ACTION_CONTRACT_UNSUPPORTED边界 |
| dispatch/manager.py | 增加input_model/proposal_validator两个后端依赖注入参数，默认仍是原V1模型/校验器；accept、snapshot、confirm_onsite以实际输入类型工作。没有重写任务/运输/容量/事件状态机 |
| dispatch/validation.py | validate_proposal增加可选input_model、required_actions、action_types；旧默认不变；同一资源选择/能力/容量校验应用于完整动作集 |
| dispatch/service.py | 原入口读取、复制输入时按显式版本解析；输出和ETA证据链不变 |
| dispatch/providers.py | Fixed/LLM Provider输入解析支持显式版本；LLM仍发送原完整JSON，只有新版本追加完整计划说明，五字段输出不变 |
| dispatch/eta.py | 仅输入边界改用版本解析；query/route/time/event/readiness语义完全未改 |

新增源码：complete_contracts.py、complete_demo.py、prompts/complete_plan.md。新增测试：tests/complete_dispatch/test_complete.py。没有改M2-A manager/models/catalog、旧dispatch/models.py、contracts/、agent/、runtime/、pulse/或原Prompt文件，也没有新增框架或Agent。

## 调度与一致性

`schedule_complete(Request, CompletePlan, provider, eta_provider)`只接受已注册的完整原计划。版本未知→CONTRACT_VERSION_UNSUPPORTED；结构/额外参数/非法动作→PLAN_SEMANTICS_INVALID；顺序→DEPENDENCY_UNMET；研究范围未知→CONSTRAINT_UNKNOWN/INDETERMINATE；身份/计划改变→IDENTITY_MISMATCH或PLAN_MISMATCH。新动作不再因旧八动作枚举而拒绝。合法计划转为原资源需求视图，再进入原schedule路径；Agent实际上接收新版完整DispatchInput，不是八动作子集。

原M2-B成功条件保持：读取两个版本→Agent建议→锁内再次检查→M2-A三值需求校验→旧ResourceManager副本accept→M2-A原子reserve→同锁发布旧任务及资产。中途失败不发布旧副本，不出现部分成功；allocated=true仍只表示真实资源分配。

缺物资、缺能力、地点不符、未知资格、旧版本分别继续使用M2-A的RESOURCE_SHORTAGE/RESOURCE_IN_USE、CAPABILITY_UNAVAILABLE、LOCATION_MISMATCH、QUALIFICATION_UNVERIFIED/CONSTRAINT_UNKNOWN、STALE_SNAPSHOT等结果。旧车/队/机构业务拒绝保留RESOURCE_UNAVAILABLE等既有码及具体原因。非法计划的错误不伪造库存冲突或医疗成功。

同一实例的SharedResourceManager仍是唯一医疗账本；同一SharedDispatchCoordinator维护唯一旧车/队/容量表。旧/新输入可以同run共同竞争同一资源，测试已覆盖；若混合版本引用相同旧资产，初始完整资产字段必须相同，不能把新能力数组裁剪给旧患者形成矛盾视图。资产身份不独立的拒绝/未知逻辑不变。

开始、消费、执行回执、停止、取消继续走原M2-A及M2-B接口。控制源动作不被当作额外耗材投入；环境移除不产生实际到达；accepted不自动扣耗材或释放；unknown继续隔离；真实消耗不能回滚。新旧版本共用原线程锁、版本、幂等请求缓存与串行执行规则，不新建事务/库存平台。

## Demo来源

complete_demo.research_plan仅构造确定性研究fixture。十类单伤配置是动作白名单，不是已排序计划：fixture在构造输入前选择既有测试过的控源后支持/插管后通气分支，液体和血液分支分开；五类复合直接使用registry的A+B序列。此fixture构造逻辑不用于转换任何用户传入计划；桥接从不重排输入。

Agent测试用已有FixedDispatchProvider和原service，LLM传输另以原LLMDispatchProvider+HTTP Mock核验。不是新救助Agent，不证明真实LLM生成完整计划。
