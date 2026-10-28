# 180秒时间协议审查

本轮先审查原始实现，再建立独立扩展。历史C1只读核验见 validation/historical_c1.json，原始run为 experiments/results/m3c1_priority_decision/m3c1-real-priority-001：A180秒治疗、181秒释放；B重查获配但未提交治疗。该历史run与SHA不回写。

| 层级 | 源码/函数 | 已存在的约束与含义 |
|---|---|---|
| Runner | src/core301/research_runtime/m3b_runner.py:initialize/execute/episode/advance_to | 60施伤、180决策、181首次机制采样、480终点；execute在非180返回UNVALIDATED_TIMING，尚未进入CaseRuntime |
| Runtime | src/core301/runtime/v2/case_runtime.py:prepare/execute_plan/advance/fork_control | prepare推进60+120；execute_plan对非noop动作在非180明确拒绝；advance不超过480；匹配control只能180分叉 |
| 范围注册 | src/core301/runtime/v2/restricted_registry.py:REGISTRY | phase1为decision_s=180、end_s=480；src/core301/pulse/v2/protocol_book.py:PROFILE_VERSION=301.v2.phase1.research.1，冻结伤情范围、患者SHA与动作配置 |
| 适配器 | src/core301/pulse/v2/treatment_adapter.py:TreatmentAdapter.convert；proxy_adapter.py:ProxyAdapter.convert | 检查原固定动作protocol ID、伤情/部位/源授权；控源生成同一RightLeg External Hemorrhage Severity0 payload，没有读取绝对时钟。没有据此获得181秒的旧合同授权 |
| 原生提交 | src/core301/pulse/v2/session.py:ResearchPulseSession._submit；src/core301/pulse/session.py:_apply | 对当前Engine提交原生动作，无180秒硬编码。是否在181秒接受并真实控源仍需独立原生实验，不由源码推断成功 |
| 机制释放 | case_runtime.py:_reconcile；research_runtime/bridge.py:SharedAuthority.finish | 当前源仍合法、同源Hemorrhage消失且TotalHemorrhageRate=0，才能确认并交M2释放；accepted本身不足 |
| 评价 | src/core301/research_runtime/evaluation.py:evaluate/verify_rules | 旧manifest硬编码action_time_s=180/evaluation_end_s=480/profile=phase1；锁定14规则及参数SHA；StandardMale不匹配独立Soldier、缺匹配control等导致NOT_EVALUABLE。不可把181实验送入此入口伪装180 |

B在181秒受阻的直接原因是工程合同拒绝（首先Runner，若直接走Runtime仍拒绝），研究证据也尚未覆盖旧协议以外的时序。不是已经证明Pulse引擎技术上不能在181执行。

三个判断必须分开：原生技术可行性需要新run的accepted、真实提交时刻、身份和后续源机制证据；新研究合同准入必须是独立protocol；正式E/P/I还需要与其匹配的患者、control、观测窗及评价证据。技术探索通过不改变旧冻结范围或正式评价资格。

本轮窄扩展设计：将原Runtime绝对时点拒绝提取为默认严格180秒的方法，默认语义与错误码不变；新DynamicTimingCaseRuntime只重载时间准入，仍调用完整原execute_plan。Runner以runtime_class及treatment_time_allowed扩展点选择此类，旧默认不变。禁止改时钟、替换源、跳过validate_capability或直接调用底层_submit来绕过原检查。

状态：M3C2_TIMING_AUDIT_PASS。动态探索是否通过以本轮新证据报告为准。
