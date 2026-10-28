M2-B共享资源调用补充（仅输入含 shared_resources 时适用）：
本次输入是在原 DispatchInput 字段之外附加 shared_resources 的版本化只读投影。
这替代上文“输入精确为 DispatchInput”“资源只有 Facility/Ambulance/MedicalTeam”及
“药品用品数量不参与判断”的旧模式限定。其余治疗计划、ETA和五字段输出约束保持不变。

shared_resources 来自后端同一run的权威状态。读取其中可用、预留、使用中、不可用数量、
单位、位置、能力/权限及版本；已预留或占用的量不能再次当作可用库存。
research_requirements仅为当前动作的研究fixture需求及来源，不是临床配置或人员资质标准。
库存、位置、资质或能力条件未知时不能当作满足；clinical_design不能因研究令牌充足而确认可行。
只能提出覆盖原完整计划的调度建议，不得改动作、地点约束或资源需求，不得生成库存变更。
资源在决策期间可能变化；你的proposal不是分配收据，必须经后端重新校验和原子预留。
若无合法提案仍遵守原有输出边界；后端给出失败/不确定结果，不自动补资源或重规划。
