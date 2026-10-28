# V2E-11、V2E-13真实Pulse验证结果

使用Pulse 4.3.2原生引擎、男性Soldier原预注册输入与锁定V1.0 AST。运行批次`batch1_11_13_v1`，未修改规则、阈值、患者或实验矩阵。所有E/P/I为固定Profile研究结果，正式评分权限未开启，不代表临床治愈或安全认证。

|规则|治疗前指标|Treatment末60秒均值|Control末60秒均值|M|F|E/P/I|安全状态|
|---|---|---|---|---|---|---|---|
|V2E-11|SpO2=96.412716%<br>PaO2=75.489288 mmHg<br>FiO2=0.20998946 1|SpO2=97.525146%<br>PaO2=96.100297 mmHg<br>FiO2=0.23454175 1|SpO2=95.955153%<br>PaO2=75.49788 mmHg<br>FiO2=0.20999011 1|True|True|E|UNRESOLVED|
|V2E-13|COHb=3.9965877 g/dL<br>ambientCO=0.005 1<br>ambientO2=0.21 1|COHb=3.5505947 g/dL<br>ambientCO=0 1<br>ambientO2=0.21 1|COHb=7.3359056 g/dL<br>ambientCO=0.005 1<br>ambientO2=0.21 1|True|True|E|UNRESOLVED|

## 实际执行状态

|新运行ID|原生状态|采样数/末窗数|证据SHA|动作回执|
|---|---|---|---|---|
|batch1_11_13_v1__alveolar_s0.4_Control|ARCHIVED|301/61|一致|无治疗动作（Control）|
|batch1_11_13_v1__alveolar_s0.4_Treatment|ARCHIVED|301/61|一致|180.00000000s accepted=True|
|batch1_11_13_v1__CO_Control|ARCHIVED|901/61|一致|无治疗动作（Control）|
|batch1_11_13_v1__CO_Treatment|ARCHIVED|901/61|一致|960.00000000s accepted=True|

## V2E-11 指标、机制与风险

|指标|Treatment末窗范围|Treatment相对自身基线变化|Treatment−Control末窗均值|
|---|---|---|---|
|SpO2|97.457655～97.578917|+1.1124301 百分点|+1.5699937 百分点|
|PaO2|95.924495～96.235817|+20.611009 mmHg|+20.602417 mmHg|
|FiO2|0.23444725～0.23460689|+0.024552297 1|+0.024551644 1|
|PaCO2|42.785241～42.804399|+2.4355486 mmHg|+3.0849077 mmHg|
|pH|7.3868846～7.3870627|-0.023168369 1|-0.029580797 1|

Treatment非相位原生事件首次/末次观测时间：`{"Tachypnea": {"first_s": 392.6199999999329, "last_s": 479.9999999998534}}`。全部逐步事件记录保留，不将首次/末次观测区间自动解释为连续事件时长。

Control非相位原生事件首次/末次观测时间：`{}`。全部逐步事件记录保留，不将首次/末次观测区间自动解释为连续事件时长。

AST错误：`[]`；执行停止/检查信息：`{"review_required": false, "reasons": [], "automatic_continuation_allowed": true}`。

## V2E-13 指标、机制与风险

|指标|Treatment末窗范围|Treatment相对自身基线变化|Treatment−Control末窗均值|
|---|---|---|---|
|COHb|3.5418001～3.5593152|-0.44599305 g/dL|-3.7853109 g/dL|
|ambientCO|0～0|-0.005 1|-0.005 1|
|ambientO2|0.21～0.21|+0 1|+0 1|
|PaO2|92.341731～92.385116|-3.825437 mmHg|-5.64136 mmHg|
|SpO2|95.506455～95.513565|-0.3532795 百分点|+1.6915922 百分点|
|PaCO2|40.47364～40.525776|-0.064496366 mmHg|+0.17053913 mmHg|
|pH|7.408516～7.4090249|+0.00062838027 1|-0.0016687703 1|
|Na|145.04441～145.07282|-0.10253824 mEq/L|-6.5264678e-05 mEq/L|

COHb末窗均值相对治疗前下降11.159346%；原单位g/dL，下降比例不等于COHb百分比，也不代表完全清除。

Treatment非相位原生事件首次/末次观测时间：`{"Hypernatremia": {"first_s": 959.9999999994169, "last_s": 1859.9999999985985}}`。全部逐步事件记录保留，不将首次/末次观测区间自动解释为连续事件时长。

Control非相位原生事件首次/末次观测时间：`{"Hypernatremia": {"first_s": 879.5199999994901, "last_s": 1859.9999999985985}}`。全部逐步事件记录保留，不将首次/末次观测区间自动解释为连续事件时长。

AST错误：`[]`；执行停止/检查信息：`{"review_required": false, "reasons": [], "automatic_continuation_allowed": true}`。

## 来源、复现与保护

原生目录：`/home/private/project-301/research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/native_campaigns/batch1_11_13_v1`。每支保留raw_requests.jsonl、raw_native_events.jsonl、capture/observations.jsonl、初末状态、actions.json、pulse.log、execution_receipt.json和SHA256.json。Treatment另含evaluation_manifest_V2E-XX.json与evaluation.json。报告目录的*_derived_observations.csv是原始采集的离线导出，不是另一批实验。

RUN_PLAN.json固定运行ID/Manifest映射及四支预算；PREFLIGHT.json记录即时预检。终端日志在本目录*_console.log。未自动重试、未执行H00或其他分支。

执行命令如下（仅记录已授权调用；已有ID不可重跑）：
```bash
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single alveolar_s0.4_Control --campaign batch1_11_13_v1 --execute
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single alveolar_s0.4_Treatment --campaign batch1_11_13_v1 --execute
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single CO_Control --campaign batch1_11_13_v1 --execute
PYTHONDONTWRITEBYTECODE=1 .venv-pulse/bin/python research_artifacts/treatment_effect_rules_v2_candidate_v0.1/independent_native_execution_driver_v1/driver.py --single CO_Treatment --campaign batch1_11_13_v1 --execute
```

运行前后1129份保护文件SHA一致；规则SHA：`6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f`。

V2E-01未重复运行；其既有真实数据的离线恢复结果为E，见log_sha_fix_v1/recovery/evaluation.json。本轮是否完成另外两条闭环，以以上实际状态和原AST结果为准；安全状态不得被疗效E覆盖。


## 本轮最终结论

4/4支原生实验成功完成，2/2组合法配对，未重试、未扩大分支。两条原AST结果均为E（M/F均true），只读重复评价与运行时结果逐字段一致；必要安全指标无缺测、已定义严重否决事件为空，但安全状态均为UNRESOLVED。结合此前V2E-01的真实数据恢复结果E，首批三条规则已完成原生数据到锁定AST的研究评价闭环。

V2E-11末窗最小SpO₂自身增益为1.044939个百分点，最小PaO₂自身增益为20.435207 mmHg；V2E-13末窗COHb平均下降11.159346%，逐点最小下降10.941147%。这些是实测描述，不是新阈值。

未解决的安全政策及观察到的不利变化仍保留，不以E宣称患者整体安全。未启动其余11条或H00，不宣称14条规则全部完成独立验证。
