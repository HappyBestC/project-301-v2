# M3-C2 本轮验证报告

本报告区分真实模型反馈、Fake控制分支、独立原生时序探索和正式疗效适用性。最终分项结论见 validation/acceptance.json；不能将Fixed或Mock结果当成真实LLM输出。

## 离线合同与控制

最终新增套件：**48 passed，70.08秒**，见 [m3c2_tests_final.log](validation/m3c2_tests_final.log)。覆盖五类冲突、四种合法反馈、错误JSON/重复key/缺字段/额外字段、错误患者/计划/run/decision/时刻/版本、非法计划修订、阶段非法操作、白名单与隐藏数据、新快照、事件等待、次数预算、错误脱敏、原181拒绝、新181准入、未列时间拒绝、范围/源身份、Unknown隔离和资源守恒。

首次套件45 passed、3 failed：负向测试试图直接修改frozen InjurySource或Literal动作字段，在进入目标校验前失败；改用合法构造的替代测试对象后48项全通过。原始日志保留在 [m3c2_tests.log](validation/m3c2_tests.log)，未通过禁用产品校验修复测试。

完整Fake闭环：[m3c2-offline-wait-recheck-001](../../experiments/results/m3c2_feedback_decision/m3c2-offline-wait-recheck-001/run_summary.json)；真实M2资源冲突→Fixed WAIT→真实管理器释放→Fixed RECHECK→新请求获配→旧181秒时窗拒绝→取消预留，两患者各301帧。54文件SHA与语义核验PASS_OFFLINE_ONLY，见 [offline_verify.json](validation/offline_verify.json)。不作为原生生理证据。

额外 [STOP未用预留检查](validation/stop_unused_check.json)实际调用M2取消RESERVED预留、恢复available、确认没有治疗。五种重新计算SHA后的语义篡改均拒绝：原文决策替换、控制事件替换、虚构唤醒、Agent观测篡改、重复治疗，见 [tamper_checks.json](validation/tamper_checks.json)。这些不是额外pytest用例，不与48相加。

## 真实反馈

run：`experiments/results/m3c2_feedback_decision/m3c2-real-feedback-001`；日志 [feedback_native.log](validation/feedback_native.log)，只读核验 [feedback_native_verify.json](validation/feedback_native_verify.json)。

真实gpt-6-sol调用2次，SDK retries=0、timeout=60、max_tokens每次1000。模型实际输出KEEP_PLAN_AND_WAIT→DEFER_INSUFFICIENT_EVIDENCE，分别绑定180秒/V3与181秒/V5。原始请求/响应/usage、ResourceFeedback、输入、解析决定及控制事件一一对应。合计服务usage7946 tokens，cost=null。

66文件SHA通过；两个独立PID；A真实180秒治疗1次，B0次；两名患者各301帧至480秒。A181秒以原生源控完成证据释放medic，B获得真实事件唤醒后模型DEFER，宿主未重新请求也未治疗B。最终资源全部归还、无重复分配或未解决allocation。

真实验证分支为WAIT、实际事件唤醒、DEFER；真实LLM RECHECK和STOP未覆盖，分别仅有离线/Fixed探索与离线证据。不声称真实模型决定让两个患者都完成治疗。

状态：M3C2_REAL_AGENT_FEEDBACK_PASS。冻结协议保持；未治疗B不强行评分，已治疗A正式评价入口仍返回NOT_EVALUABLE。

## 独立时序技术探索

run：`experiments/results/m3c2_feedback_decision/m3c2-timing-exploratory-001`；日志 [timing_exploratory.log](validation/timing_exploratory.log)，核验 [timing_exploratory_verify.json](validation/timing_exploratory_verify.json)。

探索启动前自动执行独立Fake/M2准入探测，保存timing_admission.json：原Runner/Runtime181拒绝，新181完整执行器通过，原/新182拒绝，患者与锁定规则SHA一致。范围/身份/Unknown由48项测试同时验证。预检本身不是原生证据。

原生探索明确使用Fixed反馈baseline，LLM调用0；新协议`301.research.dynamic_timing.m3c2.1`。A180秒提交、181秒机制确认并释放；B181秒重新获配并提交、182秒机制确认并释放。两份执行回执写入新protocol_version和exploratory标记，同时沿用固定payload协议。两患者观察至480秒，各301帧，65文件SHA、身份、时钟、M2守恒与不重复治疗由独立工具核对并通过。状态M3C2_TIMING_EXPLORATORY_PASS与M3C2_DUAL_PATIENT_DYNAMIC_EXECUTION_PASS仅适用于这份明确Fixed反馈的独立探索。

只验证本场景离散181秒技术可行性及对应有限双患者动态执行。181秒至480秒为299秒，缺少匹配control/可适用正式评价证据，探索不调用旧硬编码180的manifest评价入口；始终NOT_EVALUABLE。EXPLORATORY不等于完整动态时序医学有效性，后者仍M3C2_TIMING_NOT_VALIDATED。

## 回归与保护

本轮全量非原生回归：**1182 passed、26 deselected、6 warnings、0 failed，651.36秒**，原始日志 [full_regression.log](validation/full_regression.log)。包含M2-A/B/C、M3-A/B/C1/C2、原Pulse适配/评价与研究Runtime测试。6个warning为既有Pulse/pkg_resources弃用警告。历史1134不作为本轮结果；48项新增测试已包含在1182内，不重复相加。26项旧native integration未执行；本轮两个双Pulse原生实验独立报告，不替代它们。

对1264项已有源码/配置/研究档案/历史实验文件审计，仅修改授权的`research_runtime/m3b_runner.py`与`runtime/v2/case_runtime.py`两个窄扩展点，无删除，见 [change_audit.json](validation/change_audit.json)。原180默认检查保留；M1/M2、原Prompt、C1排序语义、PulseWorker/适配器、十伤/五复合配置、12动作固定参数、14规则、患者SHA及历史run保持不变。

历史证据本轮只读复核：[M3-A](validation/historical_m3a.json)、[M3-B](validation/historical_m3b.json)、[M3-C1](validation/historical_c1_after.json)，均通过。未读取或修改原project-301。

补充保护实测：[准入缺失阻断](validation/admission_failure_check.json)证明预检失败不启动原生Worker；[旧完整Runtime181拒绝](validation/frozen_executor_check.json)直接调用原CompleteExecutionBridge→CaseRuntime执行入口，仍返回UNVALIDATED_TIMING且治疗提交0。这两项均明确为离线检查，不增加pytest用例计数。
