# M2-C 实际测试报告

2026-10-19，现有 `.venv-pulse/bin/python` / pytest 环境。没有安装依赖、真实LLM/API调用、Pulse实验或Unity。本轮Mock LLM使用httpx.MockTransport，原Runtime回归使用既有替身。

## 最终结果

| 测试集 | 通过 | 失败/错误 | 跳过 | JUnit耗时 |
|---|---:|---:|---:|---:|
| M2-C新增合同/集成 | 45 | 0 | 0 | 2.306秒 |
| M2-A、M2-B及原调度/合同/Runtime回归 | 633 | 0 | 0 | 19.519秒 |
| 合计 | **678** | **0** | **0** | — |

原633项包含M2-A 46、M2-B 44、其余543项。初轮M2-C 40项通过，补充三mode生命周期、同run混合版本竞争和真实LLM Provider HTTP Mock后最终45项；不重复累计前轮运行数。没有删除旧测试、修改旧预期或放宽规则换取通过。

原始证据：[new_tests.log](new_tests.log)、[new_tests.xml](new_tests.xml)、[regression.log](regression.log)、[regression.xml](regression.xml)。机器摘要：[RESULTS.json](RESULTS.json)。无未解决测试失败；未实现层次见LIMITATIONS。

## 命令

在项目根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/complete_dispatch -o cache_dir=/tmp/301-m2c-tests --junitxml=research_artifacts/resource_model_m2c/new_tests.xml

PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m pytest -q tests/shared_dispatch tests/shared_resources tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -o cache_dir=/tmp/301-m2c-regression --junitxml=research_artifacts/resource_model_m2c/regression.xml

PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python -m core301.dispatch.complete_demo
```

## 十二动作和五类复合覆盖

`test_complete_profile_roundtrip_agent_receives_all_actions_and_real_reserve`逐一覆盖十类单伤和五类复合；`test_all_twelve_actions_and_transfusion_have_actual_allocation_coverage`补血液分支，断言覆盖集精确等于十二正式动作。

另实际运行17个独立研究资源场景（十类单伤默认分支、五类复合AB、两类出血的血液分支），每个都通过新合同→原Agent入口→原协调器→真实M2-A.reserve。完整输入、分配结果、状态/allocations在[COVERAGE.json](COVERAGE.json)。17次都allocated=true；这17次是独立验证运行，不额外加到pytest通过数中。

| 复合scope | 完整正式序列 | 合同 | 需求解析/Agent传递 | 研究fixture原子预留 | 缺物资负向测试 |
|---|---|---|---|---|---|
| penetrating_thoracic_composite_v2 | occlusive_dressing → control_hemothorax_bleeding → chest_tube | PASS | PASS | PASS | PASS，整组失败 |
| blunt_thoracoabdominal_composite_v2 | control_internal_bleeding → fluid_resuscitation → needle_decompression | PASS | PASS | PASS | PASS，整组失败 |
| blast_hemorrhage_respiratory_composite_v2 | control_external_bleeding → fluid_resuscitation → intubation → mechanical_ventilation | PASS | PASS | PASS | PASS，整组失败 |
| fire_co_alveolar_composite_v2 | remove_from_exposure → supplemental_oxygen | PASS | PASS | PASS | PASS，整组失败 |
| trapped_hypoxia_dehydration_composite_v2 | remove_from_exposure → fluid_resuscitation | PASS | PASS | PASS | PASS，整组失败 |

成功场景明确为research_fixture：足量研究令牌、同地点、显式能力/权限及暴露路径/接收环境凭据。没有通过更改固定AB、跳过临床未知或隐式合并团队成员来达到5/5。上述PASS仅到合同和研究资源预留层；真实救助LLM生成与Pulse执行未测试。缺参数/资质、地点不符、实际身份重叠等仍受原限制。

## 验收测试索引

以下均在tests/complete_dispatch/test_complete.py。

| 验收点 | 测试 | 真实断言 |
|---|---|---|
| 全动作/无损序列 | test_complete_profile_roundtrip_agent_receives_all_actions_and_real_reserve（15scope） | JSON往返、M2-A需求往返相等；Provider收到完整原计划；原管理器生成全部实例及allocation |
| 第十二动作及血液分支 | test_all_twelve_actions_and_transfusion_have_actual_allocation_coverage | 覆盖集合精确等于Catalog及十二枚举；真实血液预留 |
| 五复合原子失败 | test_composite_last_resource_missing_rejects_entire_plan（5scope） | 删除后续动作所需资源后失败；账本、车和床位均无部分预留 |
| 版本/动作/参数/目标错误 | test_invalid_semantics_return_structured_failure_without_reserve（10参数） | 乱序、错侧、native参数注入、缺依赖、重ID、albuterol、未知动作、未知版本、未知scope、互斥分别拒绝；无账本变化 |
| 依赖不能靠改ID绕过 | test_reordered_sequence_with_repaired_ids_still_rejected_by_existing_rules | 重建serial声明仍不能绕过血胸、气道、控源、复合固定序列规则 |
| 旧/新版本与有损转换 | test_explicit_legacy_bridge_and_lossy_downgrade_refused | V1按原解析；显式上桥接相等；未知版本及向V1丢metadata的转换拒绝 |
| 临床未知及资产独立性未知 | test_clinical_unknown_and_unsafe_asset_identity_remain_blocked | INDETERMINATE，不把fixture能力当临床资质 |
| 幂等/竞争/取消 | test_competition_idempotency_cancel_and_retry | 同请求同task，不重复预留；B冲突；A未用取消后B成功 |
| 线程竞争 | test_threaded_complete_plans_do_not_overallocate | 两线程Barrier同快照申请，唯一完整成功，无超额预留 |
| 决策期间资源改变 | test_resource_change_during_full_plan_decision_is_rechecked | 原Agent决策期间设备不可用事件推进版本；STALE_SNAPSHOT，无预留 |
| 真实消耗与未知隔离 | test_unknown_execution_isolated_and_consumption_not_rolled_back | 控源accepted/释放后开始胸管；实际开包计耗；unknown后fail保留人员隔离和消耗 |
| 禁止Agent改计划 | test_provider_cannot_modify_original_complete_plan | Provider尝试修改收到的副本，不改变原计划或后端全部动作需求 |
| 新合同沿用旧生命周期 | test_complete_legacy_assets_and_cancellation_use_existing_lifecycle（三mode） | 真实队/车/机构占用，取消/onsite完成与episode结束释放原语义保持 |
| 同run混合版本同账本 | test_old_and_complete_plans_in_same_run_compete_in_one_ledger | V1患者先分配，新完整计划患者观察同一medic占用并失败，无第二份库存 |
| 原LLM Provider载荷 | test_real_llm_provider_sends_complete_contract_via_offline_http_mock | 原SDK HTTP Mock收到完整三动作/ID/依赖/scope，随后真实后台预留 |
| 完整Demo | test_demo_uses_nonlegacy_actions_and_real_state | 输入与Agent收到的计划完全相等；A资源版本0→1；B实际拒绝 |

原M2-A/M2-B回归继续验证各资源守恒、负数/NaN拒绝、多视图引用、真实消耗不自动恢复、事件/ETA/接收、不同run隔离和身份等限制。

## Demo真实结果

[demo_output.jsonl](demo_output.jsonl)两条JSON记录，每条含完整输入、Provider实际收到的计划、结果及前后真实资源状态。

| 请求 | 完整动作数 | 输入/Agent计划相同 | allocated | 资源版本变化 | 结果 |
|---|---:|---|---|---|---|
| A | 3 | 是 | true | 0→1 | medic、occlusive_dressing_kit、chest_tube_kit真实预留 |
| B | 3 | 是 | false | 1→1 | RESOURCE_IN_USE，含A的真实allocation标识，无新分配 |

动作包含旧合同不能表达的control_hemothorax_bleeding；未删除它，亦没有只将chest_tube下传。独立核对两条记录所有资源的两条数量守恒式均成立。Demo未提交任何native动作，不代表治疗完成。

## 文件保护

实施前记录18081个既有文件SHA，实施后仅6个必要dispatch源码文件变化，18075个一致。明细和前后SHA见[SOURCE_PROTECTION.json](SOURCE_PROTECTION.json)。覆盖core301、config、M1/M2-A/M2-B产物、十类/五类基线及两版规则研究目录。旧contracts/、dispatch/models.py、agent/、runtime/、pulse/、M2-A资源实现、原Prompt、冻结配置/疗效规则均未改。不是整个Pulse安装树审计。

## 最终逐层状态

合同表达PASS；组合校验PASS；完整资源映射PASS；现有调度入口集成PASS（Fixed/HTTP Mock）；原子分配PASS；旧合同兼容PASS；五复合合同/研究资源层PASS。救助Agent新版实际输出PARTIAL（仅旧桥接/fixture，真实LLM仍V1）；Pulse新合同执行BLOCKED/未接入未运行。详细限制见LIMITATIONS.md，不以678通过掩盖这些边界。
