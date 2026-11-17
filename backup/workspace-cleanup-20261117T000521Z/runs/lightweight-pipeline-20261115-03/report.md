# 新 CSV 候选轻量 Pipeline 验收

**Pipeline 是否完整执行到最终 Controller 决策：否。至少一个新候选是否真正 Accepted：否。**

仅尝试 1 个候选，成功生成 1 个。Controller 输出：`needs_review`，原因：`TEST_LOOP_NEEDS_REVIEW`。早期失败时保存 Controller 结果不等于完成终验。

## 阶段结果

| 阶段 | 实际状态 |
| --- | --- |
| preflight | ready |
| synthesis | candidate_generated |
| instruction_consistency | no_findings |
| test_generation | tests_generated |
| docker_test_gate | needs_review |
| challenge | not_run |
| independent_reviewer | not_run |
| repair | not_run_or_not_authorized |
| final_docker | not_run |
| final_harbor | not_run_or_incomplete |
| controller | returned |

一致性检查为 no_findings 时仅表示现有有限规则未发现冲突，不是任意自然语言规范已获证明。Reviewer 为现有 Challenge 独立 Contract 见证审查；未到该阶段则不计已运行。

## 具体阻塞证据

- {"stage": "test_execution", "reason": {"type": "TEST_LOOP_NEEDS_REVIEW", "message": "The failing test `test_empty_input_file_produces_only_header` asserts that an empty (0-byte) input file produces only the header and exits 0. However, the Contract's input_spec states input is a UTF-8 CSV whose header is exactly `email,name`, and that input \"可以仅有表头\" (may be header-only) — it does not authorize a completely empty file with no header row at all. The test therefore appears to demand behavior beyond the contract (or at least the contract is ambiguous about zero-byte input), and the responsible component (implementation vs. test) cannot be determined from the supplied snippets. Additionally, repair_permission is analysis_only, so a diagnosis must not be issued. Stopping for review."}, "evidence": "verification/run_result.json"}
- {"stage": "docker_test_gate_or_diagnosis", "reason": "The failing test `test_empty_input_file_produces_only_header` asserts that an empty (0-byte) input file produces only the header and exits 0. However, the Contract's input_spec states input is a UTF-8 CSV whose header is exactly `email,name`, and that input \"可以仅有表头\" (may be header-only) — it does not authorize a completely empty file with no header row at all. The test therefore appears to demand behavior beyond the contract (or at least the contract is ambiguous about zero-byte input), and the responsible component (implementation vs. test) cannot be determined from the supplied snippets. Additionally, repair_permission is analysis_only, so a diagnosis must not be issued. Stopping for review.", "evidence": "verification/test-loop.json"}
- {"stage": "controller", "reason": "TEST_LOOP_NEEDS_REVIEW", "details": ["Test repair stopped without passing the Docker gate."], "evidence": "verification/decision.json"}

## 预算与记录

实际网络模型调用 17/30；按阶段：{'synthesis': 9, 'test_generation': 7, 'test_diagnosis': 1}。已知 prompt tokens=77385、completion tokens=7665、total tokens=85050/240000。usage 完整：True；未知 usage 的请求：[]。未知用量不视为零，后续请求停止以保护预算。

本次真实请求均正常，无网络失败或重试；不是预算耗尽。新增一致性门禁正常运行，未发现有限规则覆盖的问题。当前阻塞来自独立测试把 0 字节输入当作合法 CSV；Contract 要求表头恰为 email,name。Oracle 因此失败，而正确对照、Nop 和违规对照符合预期，触发现有 analysis_only 限制。Test Agent 仅用一次只读诊断调用便请求复核，没有授权或执行 Repair。Challenge、独立 Reviewer 及双后端终验均未到达。

单次输出上限 7000 tokens；诊断请求遵守 24 KiB 输入及 2000 输出 tokens 限制。Challenge 最多 2 次，Repair 最多 1 轮，最终 Docker/Harbor 各一轮；此前门槛失败时不绕过门槛补跑终验。预算调用包含实际失败请求，所有原始请求/响应、usage、错误及停止事件见 model-calls.jsonl。

复用现有 CSV Plan/Contract、SynthesisAgent、verify(all)、确定性 Controller 和现有独立对照准备工具。生产源码运行期间未变更：True；原始 Contract 未修改：True。未重置预算、生成第二候选或放宽标准。source-snapshot/ 和 source-manifest.json 固定本次代码；Docker/Harbor 预检与实际评分分别记录，不混为验收通过。

只读诊断使用 1 次真实调用，usage={"prompt_tokens": 2452, "completion_tokens": 185, "total_tokens": 2637, "prompt_tokens_details": {"cached_tokens": 0}}。当前客户端可靠性故障注入结果见 ../client-reliability-20261115-01/report.md；Mock 通过与本次候选未 Accepted 分别报告。
