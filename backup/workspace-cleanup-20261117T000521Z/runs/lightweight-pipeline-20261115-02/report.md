# 新 CSV 候选轻量 Pipeline 验收

**Pipeline 是否完整执行到最终 Controller 决策：否。至少一个新候选是否真正 Accepted：否。**

仅尝试 1 个候选，成功生成 0 个。Controller 输出：`not_run`，原因：`not_run`。早期失败时保存 Controller 结果不等于完成终验。

## 阶段结果

| 阶段 | 实际状态 |
| --- | --- |
| preflight | ready |
| synthesis | error |
| instruction_consistency | not_run |
| test_generation | not_run |
| docker_test_gate | not_run |
| challenge | not_run |
| independent_reviewer | not_run |
| repair | not_run_or_not_authorized |
| final_docker | not_run |
| final_harbor | not_run_or_incomplete |
| controller | not_run |

一致性检查为 no_findings 时仅表示现有有限规则未发现冲突，不是任意自然语言规范已获证明。Reviewer 为现有 Challenge 独立 Contract 见证审查；未到该阶段则不计已运行。

## 具体阻塞证据

- {"stage": "synthesis", "reason": {"type": "SynthesisError", "message": "model API unavailable (URLError)"}, "evidence": "candidate/synthesis.json"}
- {"stage": "synthesis", "call": 6, "reason": "model API unavailable (URLError)", "type": "SynthesisError", "wall_sec": 120.05228517500018, "evidence": "model-calls.jsonl"}

## 预算与记录

实际网络模型调用 6/30；按阶段：{'synthesis': 6}。已知 prompt tokens=10278、completion tokens=1173、total tokens=11451/240000。usage 完整：False；未知 usage 的请求：[6]。未知用量不视为零，后续请求停止以保护预算。

本次因第 6 次模型 API 传输失败（等待约 120.05 秒后返回 URLError）停止，不是调用次数或已知 token 预算耗尽。候选尚未生成 instruction 或完成自检，因此一致性门禁未到达，不能声称本次已验证该门禁。

单次输出上限 7000 tokens；诊断请求遵守 24 KiB 输入及 2000 输出 tokens 限制。Challenge 最多 2 次，Repair 最多 1 轮，最终 Docker/Harbor 各一轮；此前门槛失败时不绕过门槛补跑终验。预算调用包含实际失败请求，所有原始请求/响应、usage、错误及停止事件见 model-calls.jsonl。

复用现有 CSV Plan/Contract、SynthesisAgent、verify(all)、确定性 Controller 和现有独立对照准备工具。生产源码运行期间未变更：True；原始 Contract 未修改：True。未重置预算、生成第二候选或放宽标准。source-snapshot/ 和 source-manifest.json 固定本次代码；Docker/Harbor 预检与实际评分分别记录，不混为验收通过。
