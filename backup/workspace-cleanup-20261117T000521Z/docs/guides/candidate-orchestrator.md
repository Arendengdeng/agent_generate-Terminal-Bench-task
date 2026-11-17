# Candidate Orchestrator 连续失败暂停

启动批次（不需要重新安装包）：

```bash
python3 -m synthesis_agent.candidate_batch \
  --plan examples/csv-repair/plan.json \
  --contract examples/csv-repair/contract.json \
  --output runs/my-candidate-batch --config config.json \
  --max-candidates 10 --max-total-tokens 500000
```

`config.json` 使用现有 `Config` 字段。`max_model_calls`、`max_tool_calls` 和
`--max-total-tokens` 是整个 Batch 的累计上限，包括生成、独立测试、传输重试和修复。
缺失 token usage 时沿用客户端的保守预留计数。密钥通过环境变量提供，不写入批次配置。
`--verification-options options.json` 可配置已有独立验证流程，例如已评审的 controls、
holdout、`repair` 和 `max_repairs`；不能覆盖共享预算、配置或验证阶段。
安装项目后也可使用 `candidate-orchestrator` 命令。

批次仅在原生 Controller 为 `accept` 且 `independent_validation=true` 时结束为 Accepted，编排器不重新判定验收。
未通过的候选标记为 `abandoned`，可继续的失败会启动下一个新候选。
每个失败候选保存 `failure_category`、`failure_reason`、`failed_stage`、
`failure_evidence`、完整运行产物清单和调用前后累计用量。分类包括
`no_progress`、`self_check_failure`、`probe_defect`、`test_generation_failure`、
`verification_failure`、`repair_exhausted`、`infrastructure_failure` 和 `budget_exhausted`。
未知归因保留 null 并转入 `needs_review`，不会作为候选质量缺陷累计。

默认连续 8 个工具操作没有改变候选文件时结束该候选；连续 3 次自检失败时停止候选内修复。
可通过 `--max-no-progress` 和 `--max-self-check-failures` 调整。
Probe 的执行异常和普通 assertion 失败分开记录；普通断言失败不足以判定 Probe 缺陷。
这些候选内守卫只在批次入口启用，现有单候选入口维持原来的限额。

相邻两个失败候选的非空分类相同时，Batch 进入 `paused_repeated_failure` 并返回，
不再创建候选、调用模型或修复。不同分类会中断连续计数。基础设施故障一次即暂停；
共享预算耗尽进入终态 `budget_exhausted`。Accepted 立即结束整个 Batch。

`batch.json` 保存状态、原始配置、累计预算、候选历史、源码指纹和恢复记录；
`candidates/NNNN/` 保存原始生成和验证结果；`diagnosis-NNNN.json` 保存诊断。
诊断是本地确定性比较，包含已确认共性、不同点、证据内容差异和可能原因，不调用模型。
相同 failure_category 仅为初步信号，报告不会将其表述为已确认的相同根因。

检查并处理失败后，显式恢复：

```bash
python3 -m synthesis_agent.candidate_batch --output runs/my-candidate-batch --resume
```

恢复只支持 `paused_repeated_failure`，复用原始配置、输入、选项、候选编号及所有用量；
不能用 CLI 调整限额或覆盖种子。恢复前核对剩余预算、输入清单、历史候选产物和历史记录摘要，
读取并记录最近的失败原因。源码指纹变化会记录在恢复事件和后续候选中，允许修复代码后继续。
历史失败连续计数不会清空；恢复后再失败一次，仍会与前一个候选比较。

基础设施暂停必须通过新的免费检查：Docker/Harbor preflight（含网络隔离能力）和 API
`GET /models` 可用性。检查失败或端点不支持该检查时继续暂停，不会仅因 `--resume` 放行。
这些检查证明依赖当前可用，不声称已确认或修复先前故障的根因。

输入 Contract、历史候选文件和原生 Controller 结果都不会被暂停或恢复覆盖；检测到历史
文件变更时拒绝恢复。每个 Batch 使用排他文件锁。进程异常中断留下 `running` 状态时，
本入口不会将其当作已经审查的暂停批次自动续跑。
