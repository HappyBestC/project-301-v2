# M2-B 实际测试报告

日期：2026-10-19。使用现有 `.venv-pulse/bin/python`，未安装依赖。全部使用 Fixed/Fake Provider、既有 Runtime 替身或 httpx.MockTransport；没有真实 LLM API、原生 Pulse 实验或 Unity 调用。

## 最终结果

| 测试集 | 通过 | 失败/错误 | 跳过 |
|---|---:|---:|---:|
| M2-B 新增集成测试 | 44 | 0 | 0 |
| M2-A 原有共享资源测试 | 46 | 0 | 0 |
| 旧调度、LLM Mock、契约、相关 Runtime 回归 | 543 | 0 | 0 |
| 合计（不重复累计历次运行） | **633** | **0** | **0** |

共享测试最终一次 JUnit 耗时 2.540 秒；旧回归 18.798 秒。初轮 36 项通过，之后补充 Mock LLM、身份重叠、预留失败注入和旧能力矛盾等边界，最终 M2-B 为44项。检查中将旧能力不足错误保留为 RESOURCE_UNAVAILABLE，避免一律误标 RESOURCE_IN_USE。最终无未解决测试失败。

原始证据：[shared_tests.log](shared_tests.log)、[shared_tests.xml](shared_tests.xml)、[regression_tests.log](regression_tests.log)、[regression_tests.xml](regression_tests.xml)、[RESULTS.json](RESULTS.json)。没有把尚未实现的临床资格、跨进程或十二动作完整调度接通算作通过。

## 运行命令

项目根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/shared_dispatch tests/shared_resources -o cache_dir=/tmp/301-m2b-pytest --junitxml=research_artifacts/resource_model_m2b/shared_tests.xml

PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -o cache_dir=/tmp/301-m2b-regression --junitxml=research_artifacts/resource_model_m2b/regression_tests.xml

PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.shared_demo
```

stdout/stderr 已分别保存。pytest 所选旧 Runtime 测试使用替身；没有选取 native/integration Pulse 用例。原 LLM 测试完全使用 HTTP Mock，新 LLM 集成测试也将 AsyncOpenAI 的 transport 替换为内存 Mock。

## 验收场景

| 场景 | 主要证据（tests/shared_dispatch/test_integration.py） | 实际验证 |
|---|---|---|
| 资源充足、B可读A占用 | test_success_shared_visibility_and_immutable_agent_view | A真实预留三类资源；B的Provider收到reserved=1/version=1；B冲突含真实blocking_allocation_ids；修改投影不影响后台 |
| 资源不足、组合原子性 | test_group_shortage_never_partially_commits（三参数） | 缺呼吸机、人员或气道包都不发布车/床位任务，不扣其他医疗资源 |
| 两伤员并发唯一设备 | test_thread_race_only_one_whole_dispatch_is_confirmed | Barrier同步两个真实线程的Agent决策，同仿真时刻；只有一个整体成功；另一个STALE_SNAPSHOT，无超配 |
| 决策期间状态变化 | test_state_changes_during_agent_decision_are_rechecked（故障、移动） | 故障/地点变化推进M2-A版本；旧快照不能确认调度 |
| Agent不可行方案 | test_impossible_agent_proposal_cannot_create_any_task | 虚构team ID被原服务拒绝；不生成预留 |
| 新旧能力矛盾 | test_legacy_capability_contradiction_does_not_publish_medical_success | M2-A物资/地点满足，但旧小队无所需能力，整体拒绝；两边都不占用 |
| 临床/能力未知 | test_unknown_is_not_success（两参数） | INDETERMINATE，不创建任务或预留 |
| 无法证明身份独立 | test_unknown_or_overlapping_ownership_fails_closed（四参数） | team/evacuation的独立性为None或False时明确未知，不能当整体成功 |
| 同canonical资产双登记 | test_same_canonical_asset_cannot_be_imported_in_both_ledgers | 旧TEAM ID与新版人员ID重叠，初始化拒绝 |
| 原子确认后半段失败 | test_reserve_failure_discards_already_validated_legacy_stage | 注入reserve失败，已校验旧副本被丢弃，不遗留车/机构预留或legacy版本变化 |
| 旧唯一队/车竞争 | test_legacy_unique_asset_is_shared_and_failure_does_not_reserve_medical（两参数） | 医疗物资足够仍被旧唯一资产占用阻止，B看到真实active_task_id |
| 机构容量不足 | test_facility_capacity_failure_has_no_medical_or_ambulance_leak | 满容量拒绝，无医疗或车占用泄漏 |
| 取消未执行任务 | test_cancel_releases_both_unstarted_ledgers_and_duplicate_does_not_repeat（三mode） | 同时释放未用医疗和旧资产；重复取消不二次改账；B随后成功 |
| 已耗/拒绝/未知执行 | test_active_medical_resources_block_legacy_release_and_consumption_never_rolls_back（三状态） | 已耗包不返还；活动或隔离存在时旧fail不释放；已知回执+停止依据后才结束 |
| 实际后送事件、接收与释放 | test_evacuation_events_readiness_admission_and_episode_release | 到站前/仅到站不能begin；接收入站释放车但保留机构占位；结束episode才释放机构 |
| 小队到达 | test_team_arrival_readiness_and_explicit_end | 到达前不就绪；合法到患者事件后就绪；end_episode按旧规则释放队伍 |
| 缺正式事件策略 | test_event_without_policy_is_rejected_without_state_change | 不猜到达，不改变状态 |
| 重复/冲突请求 | test_same_request_and_changed_key_never_duplicate_tasks；test_inflight_duplicate_is_not_a_second_agent_call | 同请求返回同task；改内容/换键重复request_id拒绝；在途重复不调用第二次Agent |
| 失败历史及快照脱离 | test_early_failure_is_idempotent_and_history_is_detached | 失败后同键改内容拒绝，修改history返回值不改内部记录 |
| run隔离 | test_runs_are_isolated | 两run相同配置可各分配唯一设备，相互不占用 |
| 不覆盖库存初值 | test_registration_never_overwrites_or_copies_different_legacy_inventory | 同run重注册或患者引用不同初始旧资源状态均拒绝 |
| 不改计划/扩动作 | test_cannot_rewrite_upstream_plan_or_location；test_unsupported_actions_are_not_dropped（五参数） | 计划顺序/动作/地点不可替换；三个实际control名称、exposure和albuterol拒绝 |
| 禁止静默回退 | test_provider_without_shared_input_does_not_silently_fallback | 不支持sidecar的旧provider在共享路径明确失败 |
| 真实LLM入口离线联调 | test_llm_existing_entry_serializes_shared_view_and_sanitizes_output | 原LLM Provider经Mock SDK发送只读sidecar和条件Prompt，保留原TreatmentPlan与五字段输出，不泄露隐藏severity/context |
| 仿真时间 | test_lifecycle_cannot_rewind_medical_time | 生命周期不得回到医疗账本已记录时间之前 |
| 完整双伤员Demo | test_demo_real_state_and_conservation | 真实申请→冲突→使用→释放→重申请→取消；每个输出资源验证两条守恒式 |

原46项M2-A测试还覆盖持续设备释放证据、实际消耗、unknown补记/隔离、幂等、单位/数值、权限变更、研究scope、全十二动作映射和多视图同资源引用。旧543项保留原DispatchInput/Proposal/Task/Event/ETA/LLM及相关Runtime行为。

## Demo 实际结果

[demo_output.jsonl](demo_output.jsonl)共14条来自实际管理器的JSON记录，通过现有 Agent 服务入口调用，不是预设结果文本。

| 步骤 | 医疗版本 | allocated（调度申请） | 呼吸机available/reserved/in_use |
|---|---:|---|---|
| 初始化 | 0 | — | 1 / 0 / 0 |
| A调度确认 | 1 | true | 0 / 1 / 0 |
| B调度冲突 | 1 | false | 0 / 1 / 0 |
| A开始通气使用 | 6 | — | 0 / 0 / 1 |
| A执行accepted | 7 | — | 0 / 0 / 1 |
| A明确停止/脱离/清理后释放 | 8 | — | 1 / 0 / 0 |
| A结束旧调度episode | 9 | — | 1 / 0 / 0 |
| B新请求调度确认 | 10 | true | 0 / 1 / 0 |
| B开始前取消 | 11 | — | 1 / 0 / 0 |

A的气道包实际消耗1，结束时仍consumed=1/total=1（初值2）。B第一次冲突含A的实际allocation ID。每条输出的全部资源已独立核对两条数量守恒式。lifecycle响应allocated=false表示没有新的分配，不表示操作失败，需看resource_result.outcome。

## 原文件保护

实施前记录1148个既有文件SHA；实施后仅3个允许修改的源码文件变化，其余1145个一致。记录见 [SOURCE_PROTECTION.json](SOURCE_PROTECTION.json)。覆盖既有core301源码、config、M1/M2-A产物及两版规则目录；冻结伤情、14条规则、救助Prompt和原调度合同均未变。不是对整个大型Pulse安装树的全量审计；工作目录没有Git元数据，因此使用前后哈希核对。

尚未支持的跨进程、重启、完整十二动作合同桥接、真实成员映射及临床资质等均列在 [LIMITATIONS.md](LIMITATIONS.md)。本轮停在M2-B。
