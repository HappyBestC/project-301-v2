# M2-A实际测试报告

日期：2026-10-19。使用已有`.venv-pulse/bin/python`（Python 3.11、Pydantic 2.12.3、pytest 8.4.2）；本轮没有安装项目依赖、调用LLM API、Unity或运行Pulse。

## 最终结果

| 测试集 | 通过 | 失败 | 错误 | 跳过 | pytest记录耗时 |
|---|---:|---:|---:|---:|---:|
| 新增共享资源测试 | 46 | 0 | 0 | 0 | 0.70秒 |
| 旧调度/合同/单病例资源相关单元回归 | 522 | 0 | 0 | 0 | 37.14秒 |
| 合计（两组互不重复） | 568 | 0 | 0 | 0 | — |

初轮38项通过；补充unknown重申请防护等边界后45项通过。最终检查修正顺序复用人员时当前使用的结束时间未清空问题，新增相应测试后46项通过。通过数仅计最终测试集，不重复累计前轮。

原始结果：[new_tests.log](new_tests.log)、[new_tests.xml](new_tests.xml)、[regression_tests.log](regression_tests.log)、[regression_tests.xml](regression_tests.xml)。机器摘要：[RESULTS.json](RESULTS.json)。本报告只陈述实际执行结果，不将未来M2-B集成列为已通过。

## 实际命令

在项目根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/shared_resources -o cache_dir=/tmp/301-m2a-pytest --junitxml=research_artifacts/resource_model_m2a/new_tests.xml

PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -o cache_dir=/tmp/301-m2a-regression --junitxml=research_artifacts/resource_model_m2a/regression_tests.xml

PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.shared_resources.demo
```

测试命令stdout/stderr保存在上述log。旧Runtime测试使用SessionFaultFixture等已有替身，不构造原生Pulse引擎；本轮没有运行test_native_*或脚本中的原生集成入口。新测试还验证调用共享服务未导入pulse.engine。

## 必须场景覆盖

| 验收场景 | 测试证据 | 实际结果 |
|---|---|---|
| 资源充足、只读检查 | test_sufficient_and_readonly_evaluation | 预留成功；evaluate前后快照及事件完全相同 |
| 资源不足、结构化原因 | test_insufficient_and_structured_conflict | RESOURCE_SHORTAGE；核对run/patient/plan/action、需求/可用量、单位、版本与来源 |
| 两伤员竞争唯一设备 | test_thread_race_only_one_winner | Barrier同步两线程；恰好一成功，另一旧版本拒绝；新请求再查得到RESOURCE_IN_USE和阻塞allocation |
| 多资源一项不足 | test_atomic_group_does_not_leak_first_resources | 整组失败，快照/分配/版本不变 |
| 设备正常结束 | test_persistent_ventilator_requires_explicit_release | accepted及plan结束均不释放；缺停止证据返回未知，完整证据后归还 |
| 消耗品实际投入 | test_actual_consumption_not_acceptance_and_no_rollback | accepted不扣量；实际consume后total减少且取消/释放均不恢复 |
| 预留后取消 | test_cancel_then_other_patient_can_reserve | 未用预留返还，另一患者可申请 |
| 失败、unknown | test_unknown_quarantines_without_restore_or_replay；test_rejected_without_consumption_needs_return_evidence | 已耗保持；未知隔离，禁止begin/release；补记事实及释放证据后可归还 |
| 重复请求 | test_idempotency_and_conflicting_keys；test_many_threads_same_idempotency_key_only_one_allocation | 相同请求不二次扣量；24次线程请求只提交一次 |
| 同键不同请求 | test_idempotency_and_conflicting_keys | IDEMPOTENCY_CONFLICT；不改库存 |
| 故障、位置变更 | test_fault_restore_move_and_version；test_fault_during_usage_does_not_free_after_restore | 旧快照失效；begin重查拒绝；修复标记不自动释放隔离 |
| 两run隔离 | test_two_runs_isolated_and_duplicate_run_rejected | 相同资源配置独立计账；一run取消不影响另一run；禁止重复初始化覆盖 |
| 临床资格/数量/地点/能力/权限未知 | test_unknown_is_never_available（5参数） | 全部INDETERMINATE，不预留，不将null变0 |
| 多视图同资产 | test_views_reference_same_inventory_and_detached_snapshots | 团队/设施视图共用同一ventilator库存；修改返回对象不改权威状态 |
| 数量守恒/补给损耗 | Harness.snapshot断言及test_received_lost_conservation_and_over_loss_atomic | 断言两条M1等式、整数非负；超量损耗整笔失败 |
| 数值与时间非法输入 | 参数化invalid_quantities/invalid_times；test_no_time_reversal_or_implicit_wallclock_expiry | 拒绝负数/bool/NaN/Infinity/字符串与倒退时间 |
| 12动作和5复合范围 | test_all_twelve_mappings_are_exercised_in_admitted_single_scopes；test_catalog_coverage_and_composite_sequential_reuse | 全部研究映射覆盖；五AB整序列以显式前序完成规则执行 |
| 保留动作/错误目标/互斥 | test_bad_scope_targets_and_disabled_action；test_conflicting_actions_and_unpaired_ventilation_rejected | albuterol、错误侧别、未验证范围、补液输血并列及无配对通气均不成功 |
| 身份/幂等绕过 | test_wrong_patient_and_duplicate_action_ids；test_new_plan_id_cannot_bypass_unknown_execution | 非所属患者拒绝；全run动作实例唯一；unknown不能换plan ID重新申请 |
| 开始前撤销权限 | test_permission_revocation_at_begin | begin重新核查，库存未消耗 |
| 部分执行后取消 | test_cancellation_of_partial_sequence_frees_unused_not_consumed | 未用呼吸机释放，已开包不回滚，正在使用人员保留到明确释放 |
| 顺序复用时间语义 | test_sequential_personnel_reuse_resets_current_usage_end_time | 前序结束后下一次begin清空当前actual_end_at_s，历史结束事实仍保留在事件中 |
| 原子消耗事件/对象防篡改 | test_invalid_mutation_is_atomic_and_no_import_of_native_engine；test_mutated_pydantic_instance_is_revalidated | 组合事件含非法allocation时不部分扣量；被篡改模型实例重新验证 |

## Demo真实结果

[demo_output.jsonl](demo_output.jsonl)共14条真实快照/结果。核心状态如下：

| 阶段 | state_version | 结果 | 呼吸机可用/预留/使用中 |
|---|---:|---|---|
| 初始 | 0 | — | 1 / 0 / 0 |
| A只读检查 | 0 | SATISFIED | 1 / 0 / 0 |
| A预留 | 1 | SATISFIED | 0 / 1 / 0 |
| B申请 | 1 | UNSATISFIED | 0 / 1 / 0 |
| A开始通气资源使用 | 6 | SATISFIED | 0 / 0 / 1 |
| A执行accepted后B再申请 | 7 | UNSATISFIED | 0 / 0 / 1 |
| A确认停止并释放 | 8 | SATISFIED | 1 / 0 / 0 |
| B重新申请 | 9 | SATISFIED | 0 / 1 / 0 |
| B开始前取消 | 10 | SATISFIED | 1 / 0 / 0 |

A实际投入的气道包consumed=1，最终未因释放恢复。对全部14条输出的每个资源另行只读核对两条数量守恒等式，全部成立。版本不因B冲突而增加；B冲突含A的真实allocation_id。

## 原文件保护与未覆盖项

实施前记录1130个既有文件SHA，实施后逐一比较全部相同（SOURCE_PROTECTION.json）。覆盖既有core301源码、config、M1目录、最终锁定规则目录及早期冻结canonical规则，不声称对整个大型Pulse安装树做了全量审计。

未测试跨进程/多机器、重启恢复、实际医疗操作、真实传感回执、Unity/Agent对接或生产性能；这些均未实现，详见LIMITATIONS.md。
