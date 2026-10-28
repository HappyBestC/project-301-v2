# V2E-07/08/09 真实Pulse验证结果

**实际完成2支：07 Control、Treatment均完成480秒并ARCHIVED；07为P。08/09未启动。覆盖由11/14推进到12/14（按既有汇总为10 E、2 P），未达到14/14。**

停止原因是原驱动的安全复核条件：07治疗后出现新的HR数值触发，`review_required=true`、`automatic_continuation_allowed=false`。不是因为P而停止，也没有将其改判为I或技术失败。没有重试或绕过该门控。

## 最小修改及实测性能

- 仅修改运行代码 `independent_native_execution_driver_v1/driver.py`：每秒公共采样与高频胸腔采样复用同刻metrics，少读301次；记录序列化/解析/写入耗时；Worker及Supervisor统一使用胸腔分支1500秒墙钟限时（原600），其他分支600秒不变。
- 仿真时序、0.02秒采样、四条完整机制通路、原生事件及原始值均未改变。代码SHA登记同步更新，旧代码及旧SHA已保存；未新增审批。
- 离线基准：2,482,065字节状态，100次JSON解析平均20.657 ms；机制JSONL单行开关/编码/写入平均0.0514 ms。I/O不是主要瓶颈。
- 旧07 Control在600秒墙钟、约354秒仿真处ABORTED。新Control耗时1095.78秒，新Treatment耗时1052.09秒，均完成480秒。旧记录完整保留。
- 这不是已证明的大幅提速：只做轻量去重，主要靠实测支持的限时修正。没有重复运行同一分支做“优化前”基准；不能将新旧不同完成范围的总耗时解释为速度提升。

|分支|高频采样数|完整序列化(s)|JSON解析(s)|机制写入(s)|指标读取/写入(s)|
|---|---:|---:|---:|---:|---:|
|open_s0.6_Control|15001|527.110|470.898|5.339|6.171|
|open_s0.6_Treatment|15001|528.832|466.222|5.491|5.677|

序列化＋解析约占整支墙钟91%–95%；08同类采集的预算按该证据准备，但08尚未实测。09亦未运行，不能宣称其性能或机制已验证。

## 原AST结果

|规则|实际分支|M|F|研究等级|独立安全状态|
|---|---|---|---|---|---|
|V2E-07|Control＋Treatment，均480秒|true|false|P|UNRESOLVED；触发安全复核停止|
|V2E-08|0，未启动|未计算|未计算|无结果|未评价|
|V2E-09|0，未启动|未计算|未计算|无结果|未评价|

07原生胸封在180.00000000001828秒accepted=true。终态与最后高频通路记录逐字段一致，`endpoint_chest_seal_proxy=true`，不只是接口接受。对应EnvironmentToLeftChestLeak原生电路阻力：`{"Resistance": {"Value": 1.0197162129779282e+95, "Unit": "cmH2O s/L", "ReadOnly": true}, "ResistanceBaseline": {"Value": 1.0197162129779282e+95, "Unit": "cmH2O s/L"}}`。这证明锁定规则限定的端点阻断代理成立，不宣称临床漏气源修复。

|指标|治疗前|Treatment末60秒均值|Control末60秒均值|
|---|---:|---:|---:|
|SpO₂ (%)|96.006240|91.550076|83.034853|
|PaO₂ (mmHg)|62.339210|55.766458|36.279551|
|MAP (mmHg)|87.050174|89.515751|76.774632|
|HR (/min)|133.167370|171.987199|192.600000|
|VT (mL)|329.534306|400.233211|399.079563|
|PaCO₂ (mmHg)|42.819044|40.396008|43.143692|
|pH|7.386751|7.409784|7.383762|

- 相对Control，SpO₂平均优势 **8.515223个百分点**，PaO₂平均优势 **19.486907 mmHg**，满足M的氧合条件及胸封代理条件。
- 相对自身基线，SpO₂平均变化 **-4.456163个百分点**，PaO₂ **-6.572752 mmHg**；自身氧合仍恶化，因此未达到F。末窗MAP最低仍比基线高2.184070 mmHg。
- 末窗取原AST的真实采样420–480秒，末点479.9999999998534秒；均值不能替代全窗条件。原AST离线复算完全一致。

## 安全及停止原因

- HR基线133.167370/min，终点171.702654/min，峰值172.379051/min。自191.000000秒起，290个公共采样触发既有140/min阈值，`new_numeric_trigger=true`。这是既有研究安全复核阈值，不是本轮新增医学标准。
- 原生事件完整保留：Hypoxia, StartOfCardiacCycle, StartOfExhale, StartOfInhale, Tachycardia, Tachypnea。五类严重否决事件为空，必需安全缺测为空。没有把UNRESOLVED说成VETO，也没有把P说成患者整体安全。
- 驱动在完成、封存、计算P后按现有安全复核政策返回非零状态并停止后续分支。当前没有发现新的采集、SHA或AST技术错误；继续08/09的实际阻塞是上述既有停止决定，未自动忽略。
- H00绑定离线验证通过但未运行08，也没有重跑H00。09将继续使用原AST的胸腔积血量20%/90%减少及末窗绝对残余≤1 mL条件，不替换成出血率。

## 测试、完整性与原始证据

- **104项离线测试通过：99项相关回归＋5项针对性测试；0失败、0跳过。** 其中32支Mock及18组比较仅是代码回归，不计为真实实验。日志：`driver_99.log`、`targeted_tests.log`。
- 另外对本次2支真实分支分别核验执行回执、适配层及全部归档SHA（Control31项、Treatment28项）；各支circuit/pleural/events各15,001行，严格递增、间隔约0.02秒；07原AST复算一致。见`REAL_EVIDENCE_CHECK.json`。
- 1113份保护文件SHA未变，包括锁定规则、AST/参数、患者、Manifest、旧07 ABORTED、原H00及旧12证据。规则SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。
- 执行命令、实际墙钟耗时、退出码及停止记录：`RUN_RESULTS.json`、`native_execution.log`。细分性能：各分支`collection_performance.json`。

原始证据根目录：`research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/chest_07_08_09_v2/`。其下：

- `open_s0.6_Control/`、`open_s0.6_Treatment/`：`raw_requests.jsonl`、`raw_native_events.jsonl`、`capture/observations.jsonl`、`capture/circuit.jsonl`、`capture/pleural.jsonl`、初态/治疗前态/终态、`pulse.log`、`execution_receipt.json`、`SHA256.json`。
- Treatment另含`raw_actions.jsonl`、`evaluation_manifest_V2E-07.json`、`evaluation.json`、`review_disposition.json`。

**本轮已停止。未运行08、09，没有重试，没有修改规则或患者配置，也没有宣布14/14完成。**
