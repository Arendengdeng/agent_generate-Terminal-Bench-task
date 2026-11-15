# 实现评估库 v2.1

保留最终 **84 个实现：30 合法、54 违规**，覆盖六种 Contract；全部 336 项 Requirement 结论已核验，标签未决为 0。

- [实现、Contract、见证与审查](v2.1/library.json)
- [精简标签与逐套评分结论](RESULTS.json)
- [自动评估使用说明](../docs/guides/implementation-library.md)
- [代码与完整证据归档](../archives/implementation-library-v2.1-20261115/README.md)

原始独立核验共 3,864 次真实 Docker CLI 执行。v2.1 仅增强分组 Requirement 检查，按代码、Contract、输入及实际产物摘要复用既有执行，没有重复计数。

19 套评估全部执行：六任务完整夹具在 Docker/Harbor 均正确接受 30 个合法、拒绝 54 个违规实现；其余人工过严/遗漏夹具符合预期。历史 CSV 套件漏检 1 个错误编码实现，并有 1 项 Docker 夹具完整性错误造成后端差异，原批次不记全部通过。

回归：227 项，212 通过、15 项外部检查跳过。开发期间撤回的 22 个旧“合法”标签及全部过程记录已归档。

本轮结论证明有限实现库与评估器的核验结果，不代表 Task Planner → Synthesis → Test → Challenge → Reviewer → Controller 已完成真实模型自动闭环。标签依据源码审查和有限独立见证，不构成一般正确性证明。
