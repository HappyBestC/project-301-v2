# 本轮测试与真实实验报告

2026-10-19（Asia/Shanghai）。结果分层，不把Mock、单患者历史结果或资源预留当作双患者治疗成功。

## 实验结果

| 层次 | 结果 | 本轮证据 |
|---|---|---|
| 双原生隔离 | PASS | m3b-isolation-002：PID 595119/595185；A单独施伤不改变B；同步180秒；关闭A后B推进181秒 |
| 正式双患者运行 | PASS | m3b-dual-native-001：PID 595347/595411；每个进程一个独立Engine；同run、同步边界，各301帧 |
| 唯一资源账本竞争 | PASS | A预留成功，B RESOURCE_IN_USE，available=0、required=1，blocking_allocation指向A |
| 释放和恢复检查 | PASS | 181秒A机制确认后释放，版本5；B新key/new snapshot恢复预留，再因时窗阻断取消；终态版本7、medic available=1 |
| A真实治疗 | PASS | 180秒control_external_bleeding一次，原生accepted，181秒source_control_confirmed |
| B真实治疗 | NOT_EXECUTED / UNVALIDATED_TIMING | 没有B治疗回执；181秒不能冒充原180秒协议 |
| 等待生理推进 | WAITING_TIME_ADVANCEMENT_VERIFIED | B的180、181秒两个真实样本，等待1秒；后续至480秒继续采样 |
| A正式评价 | 调用成功，NOT_EVALUABLE | 原适配器退出码0，MANIFEST_PATIENT_INPUT；没有E/P/I结论 |
| B评价适用性 | NOT_EVALUABLE，不调用 | 动态未治疗分支不适用锁定治疗评分，明确记录原因 |
| 原生只读验证 | PASS | validation/native_verify.json：57文件SHA及身份、时钟、资源和等待因果 |

B等待期间的独立机制数据（mL、mL/s，来自B的Pulse，不用于Agent输入）：

| 指标 | 180秒 | 181秒 |
|---|---:|---:|
| B累计失血 | 173.0659699721137 | 174.45268862582802 |
| B出血率 | 1.3875565623723651 | 1.3873850363138653 |
| B血容量 | 5323.103896316768 | 5321.759231527766 |
| A出血率 | 1.3875565623723651 | 0.0 |

等待180→181秒由资源拒绝与释放事件定义；181→480秒是时窗阻断后的未治疗观察。不能将整段300秒都报告为资源占用或等待。

## 自动化测试

初版新增M3-B定向集：22 passed、0 failed，见 validation/m3b_tests.log。随后增加中止残留Allocation、run复用/真实模式拒绝故障注入测试，以及在已有闭环用例中加入只读验证和篡改拒绝断言，共24项M3-B用例。

首次全量回归为1100 passed、1 failed、26 deselected（validation/full_regression.log）。失败是直接构造中央host的测试fixture未提供public runner通常生成的run_manifest.json，导致新只读核验器拒绝；未涉及真实实验或生产Runner故障。修复fixture补上明确offline manifest，没有放宽核验逻辑，随后重新运行全量。最终结果见 validation/full_regression_final.log（汇总在下方最终确认段）。

覆盖内容：单份库存、A/B实际M2竞争、阻塞分配身份、新版本与新幂等键、旧失败请求仍失败、重复请求不重复预留、治疗最多一次、未获资源不能治疗、跨患者计划/回执/Worker绑定拒绝、accepted不能释放、时钟倒退/跳过事件/NaN/越终点拒绝、墙上时间不影响仿真、初始失败/推进失败/漂移、Worker超时/中断/错身份/原生异常不确定、Unknown隔离、推进中止遗留Allocation、事件预算、B越时治疗阻断、完整导出与SHA篡改拦截。

故障注入属于离线测试；没有在真实患者实验中制造第二次未知治疗或伪造原生失败。26项旧integration未执行；独立双原生Smoke和dual_native不等于这26项测试通过。全量包含M2-A/B/C、CompletePlan、SharedDispatchCoordinator、原Research Runtime、M3-A离线、Pulse适配及评价接口。

## 保护与复核

validation/change_audit.json核对838个既有src/config/research_artifacts文件，无修改、无删除，14条规则SHA验证通过。所有新代码局限research_runtime及tests/m3b；没有读取原横向工程，没有调用真实LLM。

真实成果为 **M3B_DUAL_PATIENT_PARTIAL**，不是M3B_DUAL_PATIENT_NATIVE_PASS。具备真实双患者与资源竞争基础，但B后续治疗被正式协议合法阻断。

## 最终确认

最终全量实际运行：**1101 passed，0 failed，26 deselected，6 warnings，99.94s**，见 [完整日志](validation/full_regression_final.log)。包含24项M3-B用例，不与初版22项或历史1077项相加。6个告警为既有pkg_resources弃用告警。未发现M3-A或M2功能回归。

## 最终二十项答复

1. 正式双患者run创建2个独立Pulse Engine；另有两次无治疗Smoke，每次2个，均独立关闭。
2. 使用两个spawn Worker进程，规避原生绑定多实例/多线程全局状态安全性未明确的问题；中央不持有原生Engine。
3. 独立状态已验证：B在仅A改变期间完整JSON语义状态不变；正式181秒A出血率0，B仍真实出血。
4. 中央唯一global_simulation_time_s驱动屏障推进，所有事件处理前核对两个实际时间；浮点容差1e-6，墙上时间不计入生理推进。
5. B等待期间确实推进，180/181秒有两份本机原生样本，累计失血增加。
6. 两人均StandardMale、RightLeg external_hemorrhage .4，单动作control_external_bleeding；固定计划，不调用LLM。
7. 中央research_scene({'medic':1})建立唯一SharedResourceManager，两个患者共享同一个Coordinator。
8. 实际竞争发生：A先预留，B真实申请失败，没有各自一份库存。
9. B首次为RESOURCE_IN_USE，required=1、available=0、resource_id=medic，blocking_allocation_ids指向A的208cd098134b47a986920484ff81f42c。
10. medic从可用1→A预留→A使用→181秒证据释放→B恢复预留→B因时窗阻断取消，最终可用1、版本7、无未解决分配。
11. A有60秒施伤和180秒控源，B只有60秒施伤，无治疗提交、无伪造治疗回执。
12. 资源等待1秒（180→181），由真实B拒绝事件和A释放事件定义；不是临床时长。181→480为时窗阻断后观察。
13. 两人均到480秒，各301帧。独立PID分别为595347、595411。
14. 原治疗时点限定180秒，B恢复资源时已181秒，UNVALIDATED_TIMING。没有扩展患者/伤情/动作准入。
15. A实际调用正式评价器，NOT_EVALUABLE / MANIFEST_PATIENT_INPUT；B动态未治疗分支不适用评分，明确不调用及原因。
16. 日志在experiments/results/m3b_dual_patient/m3b-dual-native-001；只读核验在validation/native_verify.json，57个文件SHA通过。
17. 最终全量1101通过、0失败、26排除；此前1个fixture失败及修复过程保留。
18. 原M3-A/M2回归通过，838个既有源码/配置/规则文件逐SHA无改动。
19. 未解决：合法延迟治疗研究协议、多患者恢复/容错、跨进程持久资源权威、多动作/多资源、不同患者验证及完整疗效证据。
20. 已具备M3-C资源竞争反馈和等待唤醒基础；若目标是排队后两人都完成治疗，需先独立验证合法时序协议。本轮没有实现M3-C。

最终：**M3B_DUAL_PATIENT_PARTIAL**；等待：**WAITING_TIME_ADVANCEMENT_VERIFIED**。完成后停止。
