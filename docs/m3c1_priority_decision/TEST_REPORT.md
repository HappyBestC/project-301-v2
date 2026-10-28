# M3-C1 本轮实测报告

2026-10-19（Asia/Shanghai）。最终状态 **M3C1_REAL_AGENT_PRIORITY_PASS**；依据 [只读聚合验收](validation/acceptance.json)，不是把 fixed 输出当作真实Agent结果。三个实验的原始run_summary均在聚合验收前保守记录PARTIAL，最终验收另存，不回写实验或历史SHA。

## 测试与回归

| 本轮实际命令/检查 | 结果 | 原始日志 |
|---|---|---|
| `pytest tests/m3c1 tests/m3a tests/m3b -q` 首轮定向 | 87 passed，150.55秒 | [targeted.log](validation/targeted.log) |
| `pytest tests/m3c1 -q` 最终新增套件 | 33 passed，116.14秒 | [m3c1_final.log](validation/m3c1_final.log) |
| `pytest -q` 最终全量非原生 | **1134 passed、26 deselected、6 warnings、0 failed**，242.78秒 | [full_regression.log](validation/full_regression.log) |
| 原有源码/配置/研究档案/历史run SHA审计 | 1021项；仅授权修改m3b_runner.py；无删除 | [change_audit.json](validation/change_audit.json) |
| 历史M3-A与M3-B只读核验 | PASS；历史SHA未重写 | [M3-A](validation/historical_m3a_verify.json)、[M3-B](validation/historical_m3b_verify.json) |
| 重新计算SHA后的语义篡改检查 | 排序替换、申请顺序、跨患者观测、重复治疗均拒绝 | [排序](validation/tamper_check.json)、[其他3项](validation/tamper_checks.json) |

首轮定向收集后补充了缺测/未来观测及禁止假观测调用真实LLM的两个测试，最终33项和全量1134项均包含补充项。各次pytest重复覆盖同一测试，不相加声称独立用例总数。1134为本轮实际全量结果，不引用历史1101作为本轮通过数。6个warning为既有Pulse/pkg_resources弃用警告。

全量包含M3-A/B、M2-A/B/C和研究Runtime保护测试。旧26项native integration仍未执行。下面三个明确的原生实验不冒充这26项测试。

新测试覆盖合法A/B、B/A；重复、缺失、未知、额外患者；非JSON、重复key、非法字段；拒绝、超时、版本过期、错误时刻；五指标/单位/缺测/未来样本保护、独立患者ID、快照副本和隐藏数据限制；HTTP Mock、Prompt/schema、单次调用、usage=null及错误脱敏；失败不预留不治疗；两个方向完整执行、真实M2竞争/释放/重查、晚到时窗阻断和每患者301帧。原M3-B套件继续覆盖幂等、跨患者身份和Unknown隔离。

## 真实模型与原生实验

| run | 排序来源 | 获配并治疗 | 等待/晚到阻断 | 原生治疗数A/B | SHA文件数 | 核验 |
|---|---|---|---|---|---|---|
| m3c1-fixed-a-native-001 | fixed_A_first | A | B | 1 / 0 | 61 | PASS |
| m3c1-fixed-b-native-001 | fixed_B_first | B | A | 0 / 1 | 61 | PASS |
| m3c1-real-priority-001 | gpt-6-sol真实调用一次 | A | B | 1 / 0 | 63 | PASS |

各run两个不同PID、独立Worker命令身份，时钟同步；各患者180—480秒共301帧。初次等待是真实RESOURCE_IN_USE，181秒在真实源控确认后释放；新版本和新幂等键重查后取消未用预留，未突破180秒。最终medic available=1、reserved=0、in_use=0，无未解决allocation。正式评价真实调用返回NOT_EVALUABLE，未强制生成E/P/I。

单独原生核验报告：[固定A](validation/fixed_a_native_verify.json)、[固定B](validation/fixed_b_native_verify.json)、[真实模型](validation/real_priority_verify.json)。[固定B离线核验](validation/fixed_b_offline_verify.json)明确标记PASS_OFFLINE_ONLY，不作为原生证据。

真实LLM请求模型和响应模型均为gpt-6-sol；单次调用，SDK重试0，超时60秒，无失败后Fixed回退。真实usage：2322 prompt、235 completion、2557 total；cost=null。请求输入与实际180秒观测的授权投影一致，模型原文与保存排序一致；实际资源申请顺序、获配allocation/task、原生执行命令身份和最终回执一致。三种实验的m3b_runner后端SHA相同。

M1映射、M2管理器/Coordinator/完整合同、M3-A源码及Prompt、PulseWorker、患者/伤情/治疗参数与14条正式规则均保持原字节。仅在V2工作，没有读取、修改或依赖原横向工程。
