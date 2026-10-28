# 独立动态时间研究协议

protocol_id：m3c2_external_rightleg_delayed_control；protocol_version：`301.research.dynamic_timing.m3c2.1`。引用旧`301.v2.phase1.research.1`的患者/伤情/动作参数，引用其固定payload协议`control_external_bleeding.phase1.1`；不扩展旧协议的时间准入。

| 项目 | 旧冻结协议 | 新探索协议 |
|---|---|---|
| 患者 | SHA固定StandardMale | 完全相同，不伪造独立患者 |
| 伤情 | 60秒RightLeg外出血.4 | 相同，仅这一伤情 |
| 动作 | 原授权动作集合/固定参数 | 仅单个control_external_bleeding/RightLeg，payload完全复用 |
| 初始决策 | 180秒 | 180秒 |
| 候选治疗时间 | 180秒 | 仅180和181秒，容差1e-6，离散候选而非连续窗口 |
| 释放条件 | 首个后续1秒采样确认源控 | 同样政策；180治疗181确认，181治疗182确认 |
| 终点/采样 | 480秒，每秒 | 480秒，每秒；181治疗后仅299秒观测，不能冒充300秒评价窗 |
| 原生执行前提 | 全部原检查、M2分配、身份与幂等 | 全部保留；另外独立协议、单一固定动作及当前源scope检查 |
| 评价 | 正式证据资格不足时NOT_EVALUABLE | 不调用硬编码180的旧manifest构造器；NOT_EVALUABLE，无正式E/P/I |
| 范围 | 旧已验证工程协议 | 技术探索；不证明医学疗效或泛化延迟治疗 |

请求/释放仍走唯一M2/Coordinator；预留不等于执行准入。Unknown保留原journal与资源隔离，禁止重新治疗、自动清空或推断失败；单侧时钟故障停止全局。禁止计划修订、剂量变化、其他动作和任意延迟时间。

探索前独立自动预检：校验患者/状态SHA、锁定规则，使用Fake Worker+真实M2验证旧181被阻断、新181可沿完整原执行器进入、新182拒绝、患者及动作范围限制；记录明确FAKE的admission证据。该预检是技术合同测试，不是原生证据或人工批准。预检失败则timing_exploratory阻断。

原生探索用固定优先级及明确标记的确定性反馈baseline，不再调用付费模型；与真实反馈旧协议实验分目录。仅在新路径技术预检通过后，真实验证A180治疗并181释放、B181获配治疗、182源控确认与释放、双时钟及资源守恒。即使通过，也只报告EXPLORATORY与相应有限双患者执行，不自动获得完整动态时序研究有效性。

设计状态：M3C2_TIMING_PROTOCOL_DESIGNED。预声明时点仅180/181；未验证的182及其他时点仍禁止。正式动态疗效适用性仍M3C2_TIMING_NOT_VALIDATED。

## 本轮实际验证层级

`experiments/results/m3c2_feedback_decision/m3c2-timing-exploratory-001`已完成独立原生探索：A实际180.00000000001828秒提交、B实际181.0000000000188秒提交（均在1e-6容差内），源控机制分别181/182秒确认，两个Worker各301帧至480秒。65文件SHA及身份、资源、时序核验通过，见validation/timing_exploratory_verify.json。

因此可报告M3C2_TIMING_EXPLORATORY_PASS及对应有限M3C2_DUAL_PATIENT_DYNAMIC_EXECUTION_PASS；不能推广到182秒、其他伤情/动作或临床有效性。正式动态时序疗效资格仍M3C2_TIMING_NOT_VALIDATED。此run的反馈是Fixed baseline、真实LLM调用0，与旧协议真实WAIT→DEFER实验分开。
