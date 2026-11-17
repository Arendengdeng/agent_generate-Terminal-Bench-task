# 2026-11-14：Test Agent 真实执行反馈与有限修复验收

本归档对应七场景验收，以及验收过程中发现的 Oracle 误归因问题及其修正复验。它验证执行反馈与修复机制，不代表评分可靠性的 A/B/C 对照实验。

|目录|原目录|目的|
|---|---|---|
|[initial-acceptance/](initial-acceptance/)|`runs/step1-acceptance-20261114`|首次真实模型、Docker/Harbor 验收；保留语法、过严、遗漏等场景，以及错误 Oracle 的首次失败。|
|[oracle-attribution-recheck/](oracle-attribution-recheck/)|`runs/step1-acceptance-20261114-oracle-fix`|增加 `analysis_only` 编辑门槛后，真实模型重新分析错误 Oracle；正确测试未修改。|
|[final-harbor-recheck/](final-harbor-recheck/)|`runs/step1-acceptance-20261114-final`|修正后的代码对最终冻结测试重新执行全部 Docker 和 Harbor 对照，不复用旧评分。|

- [历史验收报告](../../../../docs/history/2026-11-14-test-agent-feedback-repair-acceptance.md)
- [机器可读最终报告](initial-acceptance/final-report.json)
- [完整实现对照矩阵](initial-acceptance/implementation-matrix.json)
- [修复历史与归因](initial-acceptance/repair-history.json)
- [逐断言索引](initial-acceptance/assertion-inventory.json)
- [最终 Harbor 运行结果](final-harbor-recheck/verification/run_result.json)
- [旧路径、新路径与逐文件 SHA-256](relocation-index.json)

归档时迁移了 921 个原始文件，逐一核对 SHA-256。原始 JSON、日志、清单和冻结源码的字节内容保持不变；其中内嵌的旧绝对路径依然存在，可用 `relocation-index.json` 查找现在的位置。921 个文件包含原有三份 evidence-manifest；本索引和本 README 是新增的归档说明。

原有三份 evidence-manifest 和 source-manifest 仍按各子目录内的相对路径校验。报告中的条件通过状态、人工确认待办、44 次 API 调用和 278,261 tokens 记录均保留；归档与重命名不构成新的模型或 Harbor 验收。

复现最终冻结评分时使用历史报告中的新归档路径，并把输出写到新的 `runs/<run_id>/`。不要覆盖这里保存的失败证据或重新生成归档中的机器报告。
