# Candidate Orchestrator 真实 LLM Batch 最终证据

最终结论：**Candidate 2 Accepted**。原生完整验证结果 `controller_decision.decision=accept`、`independent_validation=true`；追加原生离线复审也是 `accept`。

本轮最多允许 3 个新候选，实际生成 2 个；没有创建第 3 个。真实模型为 `deepseek-flash`，Plan/Contract 原样来自 `examples/csv-repair/`。已审查反馈正/反和 holdout 正/反对照全部启用。没有修改原生 Controller 判定逻辑。

## 执行结果

| 候选 | 最终结果 | 失败阶段或通过路径 | 自动修复 | 模型调用 | tokens | 候选结束后的剩余预算 |
| --- | --- | --- | --- | ---: | ---: | --- |
| 1 | Abandoned | self_check_failure：3 次自检未通过；R2/R4 的 CSV 引号字段期望与实际解析结果不一致 | 自检失败后自动改写 Probe 2 次，仍未通过 | 15 | 119,978 | 75 次调用 / 480,022 tokens |
| 2 | Accepted | Synthesis 自检 → 独立 Test → Docker 测试门禁 → 真实 Challenge → 最终 Docker/Harbor → 原生 Controller 与离线复审 | 初始 Test 门禁无需修复；Challenge 确认 R2 缺口后完成 1 轮增补测试修复 | 39 | 308,716 | 36 次调用 / 171,306 tokens |

没有触发连续同类失败暂停：首个失败后启动新候选，第二个候选成功。没有实际执行 Resume；保留历史和累计预算的 Resume 行为通过离线测试验证。

## 本轮实际发现和修复的问题

1. 失败候选状态改为 `abandoned`，保留对旧 `failed` 历史的连续失败检测兼容。
2. Accepted 入口同时要求原生 Controller `accept` 和 `independent_validation is True`，缺少任一条件均不能接受。
3. 公共配置中的 tuple 序列化为 JSON list 后导致摘要比较失败：统一配置的 JSON 表示，未修改 Controller 标准。此前 6 项修复验收回归失败随之消除。
4. 原生完整 pipeline 实时判为 accept，但原生离线复审发现最终 Harbor 漏掉已确认的 Challenge 错误实现。补齐正常 pipeline 的终验调用；原 Batch、候选、测试和原 Controller 结果保持不变。

第 4 项修复后的终验使用**同一个候选、同一份已修复冻结测试**，先后通过原生 `verify_campaign` 核验真实 Challenge 证据，并将其确认的错误实现纳入完整已审查对照。然后在新目录完整重跑最终 Docker 与 Harbor（各 7 个对象）。没有重新生成候选、测试或 Challenge，也没有跳过之前已真实执行的 Test/Challenge。该补跑新增付费模型调用 **0**，复用了原累计预算。

原始在线 accept、原始离线 error 均保留，最终主张以新终验和新离线复审为准。原始 Batch 账本没有覆写。

## 最终终验

原生 Docker：7/7 完成且符合预期。Harbor：

| 对象 | 状态 | reward |
| --- | --- | ---: |
| oracle | completed | 1 |
| nop | completed | 0 |
| known-000 | completed | 1 |
| holdout-correct-000 | completed | 1 |
| invalid-000 | completed | 0 |
| holdout-invalid-000 | completed | 0 |
| invalid-001 | completed | 0 |

`invalid-001` 是真实 Challenge 经独立见证、Reviewer、Controller 确认的错误实现。修复后的测试在两个后端均将其判为 0。

## 预算与完整性

- 共享硬上限：90 次模型调用、600,000 tokens、300 次工具调用。
- 实际累计：54 次模型调用，428,694 tokens（prompt 401,272；completion 27,422），67 次工具调用。
- 剩余：36 次调用、171,306 tokens、233 次工具调用。
- API 逐次审计：54 次真实请求、54 次成功，记录中的 token 求和与 Batch 账本一致；无未知用量预留。
- 最终补跑前后累计预算完全相同。原 Batch、历史候选及原 Controller 结果逐文件摘要完全相同。
- 原始 Plan、Contract、对照实现和审查证据全部保持原样；Controller 源码没有变更。

## 离线验证

- 批次、原生 pipeline、修复、对照、Challenge：90 项完成，2 项跳过，失败 0；实时问题修复后再次运行通过。
- Synthesis、模型客户端、指令一致性：35 项完成，1 项跳过，失败 0。
- 包含 Abandoned 后新建候选、连续同类失败暂停、Resume 累计预算与历史保留、原生完整验证接入，以及 Accepted 双条件的正反例。

## 关键证据

- [最终证据汇总](final-evidence-summary.json)
- [最终原生运行结果](frozen-final-verification/run_result.json)
- [最终原生 Controller](frozen-final-verification/decision.json)
- [最终原生离线复审](frozen-final-native-review/decision.json)
- [最终 Docker](frozen-final-verification/final-docker/execution.json)
- [最终 Harbor](frozen-final-verification/harbor-trials.json)
- [真实 Test/Challenge 原始完整运行](batch/candidates/0002/verification/run_result.json)
- [真实 Challenge 及修复](batch/candidates/0002/verification/challenge/challenge-report.json)
- [原始离线复审的真实失败](native-offline-review/decision.json)
- [批次历史及累计预算](batch/batch.json)
- [逐次 API 用量核对](usage-audit.json)
- [冻结终验前置记录与原 Batch 摘要](frozen-revalidation-protocol.json)
- [原始输入和审查证据的最终完整性](final-original-evidence-integrity.json)
- [修复后的离线测试日志](offline-tests-after-live-fix.log)
- [真实批次执行入口](run_batch.py)、[冻结终验执行入口](revalidate_frozen.py)
