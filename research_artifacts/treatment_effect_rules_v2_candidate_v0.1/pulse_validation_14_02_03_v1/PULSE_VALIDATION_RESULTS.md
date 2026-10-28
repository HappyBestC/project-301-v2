# V2E-14、02、03真实Pulse验证结果

**本轮实际运行2支原生实验：V2E-14 Control和Treatment，均完成660秒仿真。AST发生技术性拒绝后已停止；02/03未运行，未重试。**

|规则|治疗前指标|Treatment末60秒指标（均值）|Control/zero末60秒指标（均值）|M/F|E/P/I|安全状态|
|---|---|---|---|---|---|---|
|V2E-14|SpO₂ 84.219670%；PaO₂ 40.170711 mmHg；环境O₂ 0.12|SpO₂ 96.145997%；PaO₂ 85.673316 mmHg；环境O₂ 0.21、CO 0|SpO₂ 79.410072%；PaO₂ 36.864099 mmHg；环境O₂ 0.12|AST未成功完成目标计算|NOT_EVALUABLE|UNRESOLVED|
|V2E-02|未运行|未取得补液分支结果|既有合法zero：CO 5.925365 L/min|未计算|未评价|未评价|
|V2E-03|未运行|未取得输血分支结果|同一合法zero：CO 5.925365 L/min|未计算|未评价|未评价|

## 真实执行与生理响应

- 引擎Pulse 4.3.2；男性Soldier原输入；新campaign `batch1_14_02_03_v1`。两支运行ID分别为`batch1_14_02_03_v1__hypoxia_Control`及`batch1_14_02_03_v1__hypoxia_Treatment`。
- 原Manifest规定：60秒施加环境O₂=0.12，**360秒撤离，660秒评价，末窗600–660秒**。原生Treatment动作于359.99999999996254秒接受，accepted=true；恢复O₂=0.21、CO=0。此浮点表示来自真实引擎，未改写原时间。
- 两支均产生301个评价观察帧、61个末窗生理采样；采集数据可用，原生过程无ERROR/FATAL，执行回执及最终SHA清单全部匹配。关闭日志SHA问题未复发。
- Treatment自身SpO₂末窗均值提升11.926326个百分点，PaO₂提升45.502606 mmHg；相对Control末窗均值分别高16.735924个百分点、48.809217 mmHg。
- Treatment末窗SpO₂范围95.782292%～96.453380%；PaO₂范围84.376425～86.790024 mmHg。
- Treatment的Hypoxia最后一次活跃观测约422.78秒，Tachycardia最后一次约425.18秒；末窗3001个原生事件快照中，Hypoxia/BrainOxygenDeficit/CriticalBrainOxygenDeficit命中数为0。**末窗低氧事件已消失这一原始数据事实可确认，但不手动替代AST疗效判定。**
- Control的Hypoxia和Tachycardia持续记录至终点。Treatment末窗HR均值83.102105/min，对照171.324887/min。其他指标与全部相位事件均保存在RESULTS.json和原始数据中。
- 已定义严重否决事件：[]；安全必要指标缺测：[]。安全状态仍UNRESOLVED，不等于医学安全通过。

## 停止原因：事件证据时间绑定问题

原AST错误：`FUTURE_OR_UNKNOWN_EVIDENCE:target_events_inactive_W`。

评价适配层`male_independent_validation_final_preparation_v1/adapter.py`为末窗低氧事件事实写入名义时间660秒，而上下文查询时间为真实末帧时间659.9999999996897秒，差值3.1025138014229015e-10秒。锁定AST严格禁止读取未来证据，因此返回NOT_EVALUABLE。日志SHA、观测数值与原生动作本身均通过检查。

原执行记录保持ARCHIVED、review_required=true，CLI退出码1；它表示数据已归档且必须停止检查，不表示疗效验证通过。未修改AST、阈值、源事件时间、原回执或评价结果；也未以血氧改善手动赋E。本轮发现问题后只进行只读定位，未继续02/03或重新运行14。

最短后续路径：修正该末窗事件事实与实际证据时间的绑定，并加入浮点终点和真正未来事件拒绝测试；随后优先利用本次完整原生数据另存离线重评价结果，无需首先重跑660秒仿真。保持原NOT_EVALUABLE记录。修复后再继续02/03。

## zero复用核查

已核验`native_campaigns/batch1_r2/external_s0.4_zero`及`log_sha_fix_v1/recovery/external_s0.4_zero_supplement.json`：患者、输入SHA、初始配置、RightLeg Severity=0.4、60秒伤情、180秒停源、480秒终点、采样和停源动作均与02/03匹配。原补充证据验证、最终文件SHA及分支读取检查通过。

因此既有zero具备合法复用的数据基础，不因旧NOT_EVALUABLE记录而否定已经审计恢复的数据，也不把它重包装为新实验。原预处理状态及其来源SHA必须用于支持治疗分支，并显式绑定旧zero补充证据。该跨campaign运行绑定尚未实际执行；由于14技术错误触发停止，本轮没有新增zero、补液或输血实验。02/03没有CO增量结果，不能声称提升达到2%或6%。Saline/Blood固定参数见RUN_PLAN.json，后续需保持独立分支。

## 原始证据与保护

原生数据目录：`/home/private/project-301/research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/batch1_14_02_03_v1`。每支保存`raw_requests.jsonl`、`raw_native_events.jsonl`、`capture/observations.jsonl`、原生动作回执、初末状态、`pulse.log`、`execution_receipt.json`及`SHA256.json`。Treatment另含`evaluation_manifest_V2E-14.json`、`evaluation.json`、`review_disposition.json`。本报告目录的`*_derived_observations.csv`是离线导出，未替换原始数据。

运行前后1254份保护文件SHA一致。规则表SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。原患者、14条规则、AST、阈值和实验矩阵未修改，无新增人工审批。

运行命令（本轮各执行一次，无自动重试）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single hypoxia_Control --campaign batch1_14_02_03_v1 --execute
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single hypoxia_Treatment --campaign batch1_14_02_03_v1 --execute
```

**当前已有成功真实研究E/P/I结果的规则仍为3条（01、11、13），尚未推进到6条。14已取得完整真实数据但评价受技术时间绑定阻断；02、03未执行。**
