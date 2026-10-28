> **历史记录：迁移时状态（2026-10-19，科研清理之前）。** 本文数字与路径不代表当前目录；最新清单见RESEARCH_CLEANUP_REPORT.md。原迁移清单/通过日志已隔离至research_baseline/history/migration，早期失败日志及原横向全树索引在清理恢复档案中。

# 迁移实际验证

结论：`V2_BASELINE_MIGRATION_PASS`，2026-10-19，Asia/Shanghai。可将project-301-v2作为下一阶段M3开发主目录；本次未开发M3。

## 环境与实际命令

新独立`.venv`，Python3.11.15，Linux x86_64；项目以editable安装在新目录。第三方依赖来自新环境，Pulse精简运行时独立安装。完整安装版本见requirements.lock.txt。

所有pytest与Demo在`/home/private/project-301-v2`执行。首先清理继承的PYTHONPATH，再由新activate脚本设置新工程src与独立Pulse绑定路径；设置PYTHONDONTWRITEBYTECODE=1、PYTHONNOUSERSITE=1。未加载旧.env，未调用真实LLM/API。

```bash
cd /home/private/project-301-v2
source scripts/activate.sh
python -m pytest -q tests/complete_dispatch tests/shared_dispatch tests/shared_resources tests/test_dispatch.py tests/test_dispatch_eta_evidence.py tests/test_dispatch_llm.py tests/test_contracts.py tests/v2/test_contracts.py tests/v2/test_runtime.py tests/v2/test_phase2_gates.py -m 'not integration' -p no:cacheprovider --junitxml=validation/m2_baseline.xml
python -m pytest -q tests -m 'not integration' -p no:cacheprovider --junitxml=validation/all_unit.xml
python -m core301.dispatch.shared_resources.demo
python -m core301.dispatch.shared_demo
python -m core301.dispatch.complete_demo
python scripts/check_demos.py
python scripts/verify_baseline.py
```

## 测试与失败处理

| 集合 | 通过 | 失败/错误 | 未执行 | 证据 |
|---|---:|---:|---:|---|
| 原M2-C验收同集合 | 678 | 0 | 0 | validation/m2_baseline.log、xml |
| 最终全量迁入单元回归 | 1028 | 0 | 26 integration deselected | validation/all_unit.log、xml |
| 规则静态/哈希完整性 | 14规则、870文件核对通过 | 0 | 非pytest计数 | validation/baseline_integrity.json |
| Demo实际输出 | 3个入口通过，30条记录 | 0 | 无真实治疗 | validation/demo_checks.json及三个jsonl |

1028包含前述678，不将两次运行相加。扩大部分包括真实Treatment Provider的离线HTTP Mock/Prompt、运行时、投影/评价、受限准入与复合伤风险测试。26项integration未运行，不把deselected记为通过。6条警告是既有pkg_resources/namespace弃用告警，无测试失败。

保留初轮失败记录，不通过删除测试或修改断言掩盖问题：

- all_unit_initial_collection_error：pytest默认导入遇到两个test_integration.py同名，1个collection错误。
- all_unit_importlib_helper_error：改为importlib后旧helper裸import需要tests路径，4个collection错误。新pyproject加入tests路径解决。
- all_unit_missing_dependencies：944通过、37失败、47错误、26 deselected。未激活Pulse绑定时旧评价器无法读取protobuf枚举，复合风险测试还有20个动态路径fixture缺失。补齐必要fixture并使用新activate环境后最终1028全部通过。

未删除任何所选回归断言，未修改冻结哈希和阈值。未执行大规模Pulse研究、历史批量重放或Unity联调。

## Demo核对

M2-A输出14条：A预留SATISFIED，B竞争UNSATISFIED/RESOURCE_IN_USE；A使用、消耗、确认停止释放后B重新预留SATISFIED。M2-B输出14条：A allocated=true，B=false；确认停止、episode结束后B重试true。M2-C输出2条：完整occlusive_dressing→control_hemothorax_bleeding→chest_tube序列与Provider收到的计划完全相同，A=true、B=false，版本分别0→1与1→1。

check_demos.py对128个资源快照逐一断言：initial+received-consumed-lost=total；available+reserved+in_use+unavailable=total。旧八动作兼容、跨新旧合同同账本、幂等与取消/unknown执行行为由原678回归实际验证。Demo的执行回执为明确fixture，不能称真实治疗。

## 源码与配置独立性

另在`/tmp`运行（无PYTHONPATH，隔离解释器）：

```bash
cd /tmp
env -u PYTHONPATH /home/private/project-301-v2/.venv/bin/python -IB /home/private/project-301-v2/scripts/check_independence.py
```

脚本通过Python审计hook拒绝打开旧工程树。逐个导入所有可发现core301模块，文件均来自新src；读取新TEN配置、五复合配置及十二动作Catalog；执行3项单伤准入与5项复合准入全部成功。实际sys.path、解释器、模块路径详见validation/independence.json。业务源码、tests、scripts未发现旧工程绝对路径引用，未把旧树加入PYTHONPATH。

`pulse`链接只指向`/home/private/pulse-4.3.2-301-runtime`；未链接旧工程源码或业务配置。历史证据/文档中的原路径只用于来源追溯；其存在不表示会读取旧工程。迁入研究算法的适配入口也经实际导入路径和SHA校验。

## Pulse运行环境

使用新venv和外部精简安装实际创建PulseSession，加载原StandardMale初态、在t=0读取五基础生理指标后关闭。记录validation/pulse_smoke.log，原生模块来自新工程的外部链接。这只证明加载/观测烟雾检查，不是新的受限治疗实验，也不证明M2-C CompletePlan已能执行。

## 完整性与原工程保护

870个迁入文件均逐项记录源/目标SHA；868字节相同，只有CLI回退路径和pyproject适配不同。十类/五类配置、所有冻结证据、两个Agent的原Prompt、M2-A/B/C及14条规则未变。锁定规则SHA为6a0fd1080f952deea6199dfdbe4772790a59507964a0d186334a86f0c63fb52f。

原114127个文件/链接记录比较：0变化、0新增、0缺失。初选835个做前后SHA，其余比较大小/mtime_ns或链接目标；保留压缩的原始记录，不宣称对全树做SHA验证。所有写操作仅在新工程、独立外部运行时或/tmp。

## 尚存边界

无阻断本次迁移的测试/依赖失败。后续跨机器运行仍需同哈希Pulse构建；没有验证互联网重编译可产生完全相同二进制。全量历史实验数据库和旧批量回放脚本未作为新基线能力交付。当前工程按源码检出方式运行，不支持仅安装wheel后脱离根目录配置/证据。

真实救助LLM仍V1；完整计划来自研究fixture或显式无损桥接；资源反馈与双Agent重规划、完整计划Pulse执行/疗效闭环、Unity联调未完成；新版十五指标尚未全Runtime激活；临床资源资质/规格/时长未知。本轮PASS只表示用户要求的受限工程迁移与独立验证完成，不提升这些能力层次。
