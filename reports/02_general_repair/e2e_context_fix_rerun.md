# 上下文修复后的真实 E2E 重跑

- experiment_id: `02_general_repair`
- run_id: `e2e-20261117T092546Z-91dc641b`
- 证据目录：`runs/02_general_repair/e2e-20261117T092546Z-91dc641b`
- Git：`042bf3b`（master；无已跟踪文件修改，原有 backup 未跟踪内容保留）
- framework_code_version: `3c44efe525b85c84be2c475d59d2943a695d63050667180ee5d014ba5147c339`
- 时间：2026-11-17T09:25:46.654753+00:00 至 2026-11-17T09:29:03.288715+00:00，共 196.634 秒。

## 结果

已执行一次新的真实 `deepseek-flash` Candidate Orchestrator 批次，从 JSONL Plan/Contract 新快照开始生成，无 seed、无历史任务替代。原生 Controller 为 **needs_review**，离线重判同为 needs_review；Orchestrator 为 **budget_exhausted / shared_budget_exhausted**，实验结果为 **incomplete**。没有 native accept，没有 accepted 导出。

本次是真正耗尽 **40 次共享模型调用**，不是此前的诊断上下文超限。没有续跑、追加预算、修改冻结代码或手动重试直至成功。通用 RepairDispatcher 已接入，但在开发测试失败后准备调查时，模型调用已耗尽；诊断模型调用、Proposal、跨模块补丁和检查点数均为 0。**无法据此验证新上下文管理在真实多轮 Repair 中的效果。**

| 验收层级 | 结果 |
|---|---|
| Repair 子系统端到端成功 | 未达成；尚未调用诊断模型 |
| 完整 Agent 原生 accept | 未达成，needs_review |
| 三轮冻结复验完整可靠性验收 | 未运行，0/3 |

## 固定条件与完整性

- 复用 `experiments/02_general_repair/e2e_protocol.json`，共享限制为 40 模型调用、120 工具调用、500,000 Token、10 候选；每候选最多 2 次跨组件修复、4 次 Challenge 尝试。最终冻结验收的 Challenge 不允许编辑测试。
- max_no_progress=8、max_self_check_failures=3；诊断上下文上限 24,576 字节未扩大。配置和 `.env` 按现有入口加载，API 密钥不进入源码归档。接口未暴露实际返回的模型标识，仅记录配置模型名。
- Docker Linux、python:3.11-slim、independent-verifier:pytest-9.2.0、Harbor 0.25.0 和模型接口预检通过。Docker/调查容器沿用原隔离配置；Harbor 预定网络模式保持 **public**，本次未进行 Harbor 评分。
- Plan/Contract、reviewed feedback/holdout 控制及协议均保存新快照和哈希；源码归档、Git 状态、公共配置及运行环境在 `provenance/`、`inputs-manifest.json`、`preflight/environment.json`。
- 原生结束时 source_integrity=true、inputs_integrity=true；事后源码摘要复核、冻结验收内容及元数据完整性检查通过。未修改原生 Controller 或执行结果。held-out 未执行、未反馈给模型。

## 候选记录

| 候选 | 流程进度 | 原生决定 | 候选停止原因 | 模型调用 | 工具调用 | Token |
|---|---|---|---|---:|---:|---:|
| 0001 | Synthesis、自检、只读 shell 调查 | not_run | no_progress：连续 8 次工具调用无持久文件变更 | 13 | 16 | 84,460 |
| 0002 | Synthesis、自检、独立开发与验收测试生成、开发 Docker 验证 | needs_review | model_call_budget_exceeded，批次 shared_budget_exhausted | 27 | 29 | 182,399 |

候选 0001 并未让整批终止，Orchestrator 自动启动候选 0002。两者失败类别不同；没有触发连续两个同类失败暂停，最终由真正的全局模型调用预算停止。

### 候选 0001：Probe 缺陷未得到模型修改

自检在初始和修复实现中均报告 object keys wrong。事后查看生成 Probe 第 62 行：`sorted(item.keys()) == ["key", "version", "value"]`。正确字段的 Python 排序结果是 `["key", "value", "version"]`，故该条件错误地拒绝合法输出；证据支持 Probe 存在缺陷。模型随后执行了七次 shell 调查，但未持久修改 Probe 或其他候选文件，与前一 self_check 合计达到 8 次无变更工具调用后停止。这属于 Synthesis 阶段的模型输出/修正不足；未进入候选生成后的通用 RepairDispatcher，也不能算一次跨模块修复失败。

### 候选 0002：自检期间调整成功，独立测试仍拒绝正确控制

自检依次为 error、failed、passed。首轮 Solution 的 solve.sh 被 shell 执行时包含 Python 语句，退出 2；下一轮入口修正后，初始环境与修复环境都通过，仍不满足“初始有缺陷”。模型继续调整初始候选，最终 Probe 对初始实现 R2/R3 失败、对修复实现 R1–R4 全通过。Probe 内容摘要未变。这里是 Synthesis 自主调整，不是通用 RepairDispatcher 补丁。

独立 Test Agent 生成 15 个开发测试节点，另一次独立 Test Agent 调用生成验收套件并冻结。开发 Docker 实际执行结果：

| 实现 | 执行状态 | 预期 reward | 实际 reward | pytest 退出码 | 失败节点数 |
|---|---|---:|---:|---:|---:|
| oracle | completed | 1 | 1 | 0 | 0 |
| nop | completed | 0 | 0 | 1 | 9 |
| known-000 | completed | 1 | 0 | 1 | 1 |
| invalid-000 | completed | 0 | 0 | 1 | 4 |

正确控制仅在 `test_latest_artifact.py::test_imports_only_stdlib` 失败。该测试设置 `sys.argv = ["latest.py"]`，随后直接 import 模块；已审核正确 CLI 在模块顶层读取 `sys.argv[1]`，子进程因此出现 IndexError 并退出 1，外层第 56 行 `assert proc.returncode == 0` 失败。Contract 要求按 CLI 路径参数运行、依赖标准库，并没有要求模块在缺少 CLI 参数时仍可安全 import。事后证据支持测试添加了 Contract 未要求的 import-safe 约束；这是宿主分析，不是 Agent 已提交的诊断或 Controller 授权。

准确区分结果：pytest 外层是正常 AssertionError，wrapper 记录 completed / reward=0 / exit=1；子进程日志包含 IndexError。没有将 null 或 pytest 执行错误记成成功拒绝。正确控制被错误拒绝，因此整套开发验证失败；Nop 与错误控制的拒绝不能补偿该失败。

## Repair、Challenge 和最终验收

通用 RepairDispatcher 在 v000 保存失败执行后调用预算检查，抛出 `BudgetExceeded(code="model_call_budget_exceeded")`，历史 stop_reason 原样记录该原因。此时 40 次调用已经全部用于 Synthesis 和两套独立测试生成，因此没有产生分析目录、诊断响应、修复 Proposal 或补丁。新上下文管理没有被实际触发，也没有 context_budget_exceeded。

| 阶段 | 本次状态 |
|---|---|
| 通用模型调查 / Proposal / 修复后回归 | not_run，调用与补丁均为 0 |
| Challenge 搜索与见证 | not_run，0 次 |
| 最终 Docker / Harbor 评分 | not_run，无分数 |
| held-out | not_run |
| 三轮冻结复验 | not_run，0/3；未达到原生 accept 前置条件 |

## 成本

| 候选 | 阶段 | 模型调用 | 工具调用 | 输入 Token | 输出 Token | 总 Token |
|---|---|---:|---:|---:|---:|---:|
| 0001 | Synthesis（含 Self-check） | 13 | 16 | 79,399 | 5,061 | 84,460 |
| 0002 | Synthesis（含 Self-check） | 16 | 16 | 110,374 | 7,669 | 118,043 |
| 0002 | 独立验收测试生成 | 5 | 6 | 25,880 | 4,377 | 30,257 |
| 0002 | 独立开发测试生成 | 6 | 7 | 30,548 | 3,551 | 34,099 |
| 合计 | | 40 | 45 | 246,201 | 20,658 | 266,859 |

总耗时 196.634 秒。Synthesis 共消耗 29/40 次调用和 202,503 Token，约占 Token 的 75.9%；开发与验收测试生成消耗余下 11 次调用。工具仍有 75 次余量，Token 仍有 233,141 余量，但共享调用上限已经触发，不能继续调用模型。没有 API 失败或重试，unknown usage=0，未知预留=0；模型调用与 Token 对账差均为 0。不估算无价格依据的货币成本。

原始驱动将 acceptance-generation 的 5 次调用归为 unattributed；本报告依据 trace 路径单列为独立验收生成，补充分项在 `postrun-analysis.json`，没有覆盖原始统计。

## 与上轮的区别及后续

上轮 `e2e-20261117T061542Z-706acadd` 在 24 次模型调用时因 24,576 字节诊断上下文限制停止，已经执行三轮调查。本轮使用提交 042bf3b 的上下文修复代码，在进入调查前耗尽 40 次共享模型调用。预算原因已经明确区分，但因真实调查未发生，**不能据本轮声称上下文修复、历史 JSONDecodeError 或其他测试异常已经在完整 Agent 中闭环解决**。不同代码版本的两轮结果不合并计算成功率。

下一步应先评估 Synthesis 的低效调查和阶段间预算安排，考虑在同样总预算内为独立诊断/Challenge 保留调用，或改善阶段反馈与行动选择；这会形成新的协议/代码版本，不能在本轮冻结后静默启用。测试生成应避免额外要求 Contract 未规定的接口行为。Probe 的字段排序错误和 import-safe 假设可作为开发回归 fixture，不能变为 JSONL 专用修复规则。

本轮仅运行正式 E2E 和事后只读验证，没有修改框架、验收标准或预算，没有追加正式批次，也没有创建 Git commit。未重复运行已通过且源码未变的 54 项框架回归；前次结果为 53 通过、1 项 opt-in 容器冒烟跳过，不能将其视作本轮实时 Repair 成功。

## 复现与证据

```bash
python3 experiments/01_e2e_reliability/run.py \
  --protocol experiments/02_general_repair/e2e_protocol.json \
  --run-id NEW_UNIQUE_RUN_ID
```

原始 `experiment-result.json`、`batch/batch.json`、各候选 trace、自检结果、`verification/repair-history.json` 和开发 execution 均在本次 run 目录。离线重判输出在 `postrun-review/`；完整性和阶段明细在 `postrun-analysis.json`。报告修改不会改变原始候选或 Controller 证据。
