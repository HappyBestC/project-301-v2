# 本轮实际验证记录

本轮新增真实Pulse run与Mock、只读证据核验分别记录，不引用历史1028结果代替本次测试。

## 结果

|验证|实际结果|证据|
|---|---|---|
|初轮桥接测试|13 passed，0 failed|开发时终端执行；最终覆盖包含于targeted|
|全量默认非原生回归|1043 passed，0 failed，26 deselected，6 warnings；50.22s|[regression.log](validation/regression.log)、[JUnit](validation/regression.xml)|
|最终针对性测试|17 passed，0 failed；5.43s|[targeted.log](validation/targeted.log)、[JUnit](validation/targeted.xml)|
|真实Pulse启动001|BLOCKED：未激活绑定，No module named PyPulse；0治疗|[失败summary](../../experiments/results/minimal_closed_loop/external-source-control-native-001/run_summary.json)|
|真实Pulse实验002|PASS：初始化、一次控源、301帧、共享记账和评价调用|[summary](../../experiments/results/minimal_closed_loop/external-source-control-native-002/run_summary.json)|
|002导出只读核验|PASS：31文件SHA、301帧/61末窗、一次原生治疗、合同/资源/评价关联|[native_evidence_check.json](validation/native_evidence_check.json)|

最终17项相对于全量执行时的15项增加了“Runner拒绝Fake原生证据”和“初始化失败导出NOT_RUN”两项测试。前者仅拒绝非真实session factory，后者补充失败导出；成功原生路径未改变。新增只读verify模块未执行原生仿真。没有重跑已完成的原生治疗，也不宣称全量1045测试已重新运行。6个warnings均为既有Pulse绑定/pkg_resources namespace弃用警告，不是失败。

## 实际命令

```bash
source scripts/activate.sh
python -B -m core301.research_runtime.runner --run-id external-source-control-native-002
python -B -m pytest -q -o cache_dir=/tmp/301-loop-regression --junitxml=docs/research_closed_loop_v1/validation/regression.xml
python -B -m pytest -q tests/research_runtime -o cache_dir=/tmp/301-loop-final --junitxml=docs/research_closed_loop_v1/validation/targeted.xml
python -B -m core301.research_runtime.verify experiments/results/minimal_closed_loop/external-source-control-native-002
```

原生命令使用的run ID已存在，禁止重跑同目录。正常复现实验请省略run-id或给新的唯一名称。

## 覆盖与边界

- `tests/research_runtime/test_bridge.py`：原CompletePlan到Provider无损；共享manager整组预留；不足/未调度/任务取消时不提交治疗；同请求幂等；错误目标/依赖/严重度/额外动作拒绝；原固定代理payload；动作实例绑定；accepted不能立即释放；原生模拟unknown/rejected保留占用且禁止重试；原机理确认后释放；数量守恒；Fake不能进入原生Runner；初始化失败明确evaluator_called=false / NOT_RUN，不伪装成评价器拒评。
- `tests/research_runtime/test_evaluation.py`：直接子进程调用未改动原adapter，缺失/非法证据只能NOT_EVALUABLE且formal_grade=null；三项锁定SHA检查。
- 全量默认回归包含M2-A/B/C、旧合同、Pulse适配、Runtime替身、原评价和所有默认非integration测试。既有耗材消耗不回滚/持续设备占用测试也运行；本版桥接不因此宣称原生补液/呼吸机已验证。
- 旧26项integration用例没有运行，明确deselected；它们包含其他伤情/旧八动作及旧反事实流程，超出本轮一个固定场景。真实原生验证由本轮Runner执行，不计入1043/17的pytest数量。
- 本次没有真实LLM调用、没有对照实验、没有健康参考实验、没有其他Severity或组合实验。

## 首次启动失败与修正

001直接用.venv解释器，未source现有activate脚本，缺PyPulse路径；失败在加载引擎前，native_action_results为空。记录原样保留。早期summary中的real_pulse=true只反映请求模式，不是实际运行证据，已发现并在源码拆分native_execution_requested与成功初始化后的real_pulse，未回写001结果。002使用正确环境成功。不是以Mock掩盖失败，也不是未知治疗自动重试。

## 实际资源与时间

实际治疗提交180.00000000001828s，原生accepted=true，仅1条治疗回执；随后机制确认。资源版本0→1预留→2使用→3接受事实→4释放→5结束时清未用预留。medic令牌保守保持至终点479.9999999998534s再释放；无消耗字段伪造，无设备强制归还。

正式评价进程exit=0且确实读取本run证据；结果NOT_EVALUABLE，MANIFEST_PATIENT_INPUT。评价调用通过与评价可评分分别报告，不修改为E/I。

## 文件保护

审查前记录934个既有文件SHA；最终对照见[protection.json](validation/protection.json)。冻结配置、M2代码、Prompt、Pulse适配器、15指标契约、14规则全部不变。只新增research_runtime模块、其测试、独立实验输出、本报告目录；未读取或写入原横向工程。
