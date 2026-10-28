# 模型输入、输出与授权

输入版本 `301.treatment.input.m3a.1`。只发送合成研究患者，无真实个人信息。本次真实 run 为 m3a-real-agent-001，输入可在 agent_input.json 与 llm_request.json 逐字段复核。

临床授权明确限于当前 registry.known() 中的 `external_hemorrhage / RightLeg`，与仿真初始化用 Severity=0.4 分开；registry 不暴露 severity。模型实际输入还包含 patient_id、180 秒当前时间及 BASIC 五项测量：

| 字段 | 原请求单位 |
|---|---|
| vitals.heart_rate | 1/min |
| vitals.respiration_rate | 1/min |
| vitals.pulse_oximetry | 1（比例） |
| vitals.systolic_arterial_pressure | mmHg |
| vitals.mean_arterial_pressure | mmHg |

每项保留 value、status、observed_at_s、unit；缺测值仍为 null。PatientObservation 原合同及适配器拒绝身份/时刻不一致、未来测量。即使后端采集其他公开字段和诊断，也不进入这个五项白名单。没有未来观测、疗效等级、内部血容量/出血率、库存、预期答案或 severity。

独立 Prompt：`src/core301/agent/prompts/treatment_decision_m3a.md`。只说明可执行动作与能力边界，不发送宿主期望输出。允许动作集合是执行准入，不构成必须选择治疗的指令。defer 与 insufficient_evidence 均可返回且会停止执行。

输出版本 `301.treatment.decision.m3a.1`：所有字段必填，额外字段拒绝。

```json
{
  "schema_version": "301.treatment.decision.m3a.1",
  "decision_type": "propose_plan",
  "actions": [{"action_type": "control_external_bleeding", "compartment": "RightLeg"}],
  "reasoning_summary": "示意解释；这不是实际模型响应",
  "refusal_reason": null
}
```

提出计划恰好一个动作；空动作、重复动作、额外动作及任何多动作排列均拒绝。本轮没有合法多动作顺序可供验证，不声称验证了复杂排序。拒绝/暂缓必须 actions=[] 且提供非空 refusal_reason。JSON 不修复、不去围栏、不填缺失字段；重复 JSON key 拒绝。

| 来源 | 字段 |
|---|---|
| 模型 | decision_type、actions.action_type、actions.compartment、reasoning_summary、refusal_reason |
| 宿主 | decision_id、run_id、patient_id、plan_id、action_instance_id、scope_kind/id、severity、location_id、execution_policy、parameter_policy、depends_on |

动作及目标逐项复制后交给正式 CompletePlan 校验。reasoning_summary 仅归档，不作为执行授权。原 V1 Provider/Prompt 不变。

## 本次真实输入与原始响应

180.00000000001828 秒采样，五项均 available：HR=75.32288609216693 1/min、RR=12.0481927710843 1/min、SpO2=0.9738632878077658、SBP=112.76229122897459 mmHg、MAP=95.02536329724997 mmHg。patient_id=m3a-real-agent-001-patient，伤情临床授权 RightLeg external_hemorrhage。未发送 severity。

以下为服务返回的完整 content（原格式存于 llm_response.json）：

```json
{"schema_version":"301.treatment.decision.m3a.1","decision_type":"propose_plan","actions":[{"action_type":"control_external_bleeding","compartment":"RightLeg"}],"reasoning_summary":"Known external hemorrhage at the RightLeg supports source control.","refusal_reason":null}
```

请求与服务回报模型均为 gpt-6-sol；只发一次请求，没有自动重试。
