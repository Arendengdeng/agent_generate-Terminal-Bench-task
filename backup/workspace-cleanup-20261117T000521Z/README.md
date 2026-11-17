# Synthesis Agent

文档入口见 [文档索引](docs/README.md)，设计规划见 [设计文档归档](docs/design/README.md)；历史任务与验证记录见 [运行记录索引](runs/README.md)。本地配置模板为 [.env.example](.env.example)，复制为 `.env` 后填写模型与密钥，并执行 `set -a; source .env; set +a` 加载到当前 shell。

根据已有 Plan、Contract 和可选参考材料，生成 Python 标准库 CLI 修复任务。所有生成代码只在受限 Linux Docker 容器内执行。成功仅表示“候选已生成并完成参考解法自检”，不代表独立验证通过。

当前功能与剩余缺口见 [Step 2 完成情况说明](docs/history/step2-status.md)。2026-11-12 离线测试 44 项通过、6 项跳过；此前用户终端真实 Docker 集成 5 项通过。

Step 3 已接入候选加载、静态检查、独立 Test Agent、Harbor 导出和 Oracle/Nop 执行入口，详见 [Step 3 使用与验证记录](docs/history/step3-status.md)。历史候选 `runs/archive/candidates/acceptance-csv-01` 已通过文件完整性与静态检查。真实 Test Agent 已生成 15 个测试并映射全部 4 条要求，导出包通过 Harbor lint。按用户要求切换 Harbor 为 public 网络后，**历史 CSV 候选已实际通过 Oracle=1、Nop=0 基础闭环验收**；测试充分性与难度仍待后续验证。

Step 2 三题型真实模型验收保持单独待办，不阻止独立验证开发。历史测试数量见各阶段记录；当前行为与验收方法见 [测试执行与修复闭环](docs/guides/test-repair.md)。

Step 3 使用项目专用 `.harbor-venv`，依赖清单为 `requirements-verification.txt`。运行前可执行 `source .harbor-venv/bin/activate`；验证入口默认使用该环境中的 Harbor，无需用户级安装。

规则式 Verification Controller 每次保存 `decision.json`，区分 `accept`、`repair`、`needs_review`、`error` 和 `not_evaluated`。Controller 的 `repair` 仍是建议；新增 Pipeline 会在最终判定前执行有界的 Test Agent 测试修复循环。接口和历史规则见 [Step 4 使用说明](docs/history/step4-status.md)。

新增显式 `--repair --max-repairs 2` 可开启跨模块 Repair Dispatcher：由 Controller 路由 Test Agent 或 Synthesis Agent，统一任务版本、修复次数和全局模型/工具调用预算。修复后重新检查，最终通过完整验证且无未决问题才可 Accept；预算耗尽保存 `needs_review`。开启该模式后，测试修复也由 Dispatcher 调度。使用方法、产物和真实验收入口见 [Repair Dispatcher](docs/repair-dispatcher.md)。

完整验证默认执行：独立生成测试 → Docker 内完整 pytest → Test Agent 诊断与测试修复（最多 2 轮）→ 全部对照重新执行 → Harbor 最终验收。诊断必须引用 Contract、当前测试位置和执行证据；歧义停止为 `needs_review`。每轮 Oracle 应通过、Nop 应失败，已确认的正确替代解法也必须全部通过。完整独立验收另要求已确认反馈组及保留组各包含正确/违规实现，且冻结测试下两个后端结果一致。修复不读取参考解法。自动测试修复还要求宿主校验 Contract 与断言的矛盾、合法和违规对照及受限补丁；仅有模型诊断或 Oracle 结果不足以授权，无法确认时保留 `needs_review`。

独立对照审查清单、保留组隔离与统计口径见 [独立对照验证](docs/guides/independent-controls.md)。仅 Oracle/Nop 通过不再判完整独立验收成功。

可重复传入 `--known-invalid <solution-dir>`，要求这些已知错误实现被正常断言失败识别；error/null 不计作正常拒绝。只有 Oracle 失败而其余对照符合预期时，执行层强制 `analysis_only`，禁止模型通过自报诊断改写测试。Step 1 实际验收、模型调用成本及保留的首次失败见 [验收报告](docs/history/2026-11-14-test-agent-feedback-repair-acceptance.md)。

```bash
python -m independent_verification --candidate runs/csv-repair --output runs/csv-verification --max-test-repairs 2
```

`all` 默认启用闭环，`--no-repair-tests` 可关闭。`run --tests` 默认只运行已有测试；增加 `--repair-tests` 才允许付费模型修复。`inspect/generate/export/decide` 不启动闭环。运行前须准备本地 `independent-verifier:pytest-9.2.0` 镜像；构建方式见 Step 3 文档。生成和修复共享调用预算，不会每轮重置。

旧的 `independent_verification/validation/` 子系统及其失效测试、示例和使用说明已移除；历史运行和审计材料保留，不作为当前接口。

历史运行可离线判定，不调用模型、Docker 或 Harbor；输出目录必须不存在：

```bash
python -m independent_verification --stage decide --report-dir runs/archive/verification/step3-public-01 --output runs/step4-review-01
```

CLI 对 `repair`、`needs_review`、`error` 返回 1，取消返回 130，调用参数或输出目录错误返回 2。`accept` 与正常的部分阶段 `not_evaluated` 返回 0；部分阶段不代表验证通过。

要求 Python 3.11+、运行中的 Linux Docker Engine、已准备的 `python:3.11-slim` 镜像，以及支持工具调用的 OpenAI 兼容接口。

配置 `SYNTHESIS_MODEL`、`SYNTHESIS_API_KEY`（可选 `SYNTHESIS_BASE_URL`），然后运行：

```bash
python -m synthesis_agent --plan examples/csv-repair/plan.json --contract examples/csv-repair/contract.json --output runs/csv-repair
```

输出目录不能已存在。其他示例见 `examples/jsonl-repair` 和 `examples/manifest-repair`，参考材料用 `--seed` 指定。

API 每次实际网络尝试在现有 trace 的 `api_attempt.details` 保存 open/read_body/parse_response 阶段、耗时、timeout、代理使用标志和脱敏异常链（包括 URLError.reason、类型及 errno）；无 trace 回调时失败事件进入标准日志。明确的临时网络错误或超时最多重试一次，退避 0.5 秒；HTTP 错误（包括 401/402）、证书错误和解析错误不重试，现有外层不会叠加重试。所有尝试计入共享调用预算；`token_usage` 是已知小计，`token_usage_complete=false` 和 `usage_unknown_attempts` 保留未知尝试；可选共享 `max_total_tokens` 使用保守预留约束未知用量，未知不等于零。

每次运行在输出目录保存 `trace.jsonl`，记录实际 Agent 构建轨迹：

- `start`、`model_request`、`model_response`：运行开始、模型调用轮次与模型提出的工具调用。
- `tool_start`、`tool_result`：模型原始调用、参数、关联的 `tool_call_id`、执行结果摘要及错误。
- `failure`、`end`：失败信息、最终状态和结束原因，包括 `finish`、预算耗尽和取消。

`sequence` 是递增事件序号，`step` 是工具调用序号，`model_call` 是模型调用轮次。
每条记录包含调用数、文件数、文件字节数的使用量与上限，以及耗时。
`synthesis.json` 包含 `trace_path` 和 `budget_used`。实际 token 用量尚未采集，
`start.token_usage` 为 `null`，不代表消耗为零。
工具输出中的长字符串先脱敏，再保存前 2000 字符、原字符数和脱敏文本哈希；
发回模型的工具结果不做摘要。轨迹不保存请求头；配置密钥、常见凭证字段、
Bearer 值和包含凭证或查询参数的 URL 会脱敏。该过滤不能识别任意未标记的秘密。
轨迹从输出目录创建后开始记录；输入校验失败等创建目录前的错误不产生轨迹。

```bash
python -m unittest discover -s tests -v
```

候选进入独立测试前默认仅检查 Contract 附录一致性。CSV 格式规则通过 Config 显式选用，例如配置 JSON 中的 `"consistency_rules": ["csv-line-endings", "csv-email-domain"]`，默认空列表，不因文本包含 `csv` 自动启用。行尾规则分别核对输入与输出，无法确定归属的分句不作阻断结论。命中后通过现有静态检查交回 Synthesis，不自动改写 instruction 或测试；`no_findings` 不是一般自然语言规范的一致性证明。规则配置属于执行配置，不写入或修改 Contract。

一般 Test Repair 在模型诊断前检查证明器能力（Contract 及当前断言形态）；不支持时保存 `needs_review / unsupported_proof_rule`，模型与工具调用不消耗预算，也不尝试修复。现有整数 stdout 与固定 JSON doubling 证明器隔离在 `independent_verification/repair_proofs/`，capability 不是修复授权；原有宿主归因、严格补丁校验和完整对照复验仍全部执行。这不扩展到任意 Contract 的自动证明。Challenge 经独立见证、Reviewer、Controller 授权的增补测试走原有独立通路。

测试诊断优先提供已确认正确对照的失败断言、局部源码、Requirement Mapping 和 Contract。已确认违规反馈实现通过时，还按 Mapping 提取相关测试函数、静态 fixture/helper 依赖及引用的数据文件；缺少具体违规 Requirement 时在预算内检查全部映射并明确标记。源码默认总计不超过 12000 UTF-8 字节（含片段字段），每片段最多 160 行；截断和静态解析局限记录在 `source_limitations`。holdout 不进入诊断，不恢复完整日志，原始反馈单独保存。诊断模式不提供文件读取、日志分页、编辑或 collect 工具；默认一次提交，仅传输失败可重试一次。`Config.max_diagnosis_calls=2`、`max_diagnosis_context_bytes=24576`、`max_diagnosis_completion_tokens=2000` 可配置，并受全局预算约束。超限或证据不足保留未决。

零模型离线回归：`.harbor-venv/bin/python -m unittest tests.test_instruction_consistency`。显式设置 `CSV_DRIFT_DOCKER_TESTS=1` 和不存在的 `CSV_DRIFT_OUTPUT` 目录可运行该模块中的有限 Docker 回归；它不会生成候选、运行完整 Pipeline 或判定 Accepted。

完整调用方式、隔离边界、工具协议、配置及真实验收命令见 [Synthesis Agent 设计.md](docs/design/2.%20Synthesis%20Agent%20%E8%AE%BE%E8%AE%A1.md)。Step 2 测试范围见 [完成情况说明](docs/history/step2-status.md)。

Challenge Agent 的职责边界、独立违规见证、Controller 归因门槛、运行参数与四组对照实验见 [Challenge Agent 说明](docs/challenge-agent.md)。普通 `all` 默认开启 Challenge；实验入口显式选择 `baseline/independent/challenge/repair`，不继承普通运行开关。完整真实模型闭环的验收状态以该说明和新运行证据为准。

通用端到端验收支持真实自主发现、受限测试健壮性准备、Repair 和三轮全新 Docker/Harbor 复验，独立执行历史 9/24 面板并报告残余漏检。入口、证据格式及当前 Docker 权限阻塞见 [端到端验收指南](docs/guides/challenge-e2e.md)。

Candidate Orchestrator 支持跨候选共享预算、连续同类失败暂停、证据诊断和显式 `--resume`；入口及恢复约束见 [批次编排说明](docs/guides/candidate-orchestrator.md)。

## 经核验的实现评估库

最终 84 个实现及精简结论见 [实现库索引](evaluation_library/README.md)，自动评估命令见 [使用说明](docs/guides/implementation-library.md)。完整过程证据及代码包见 [本轮归档](runs/archive/legacy/implementation-library-v2.1-20261115/README.md)。

## 工作区与归档

共享规则见 [AGENTS.md](AGENTS.md)，目录规则见 [REPO_STRUCTURE.md](docs/REPO_STRUCTURE.md)。
当前进展见 [实现与实验进展](reports/implementation-progress.md)，归档和清理记录见 [工作区整理记录](reports/workspace-cleanup.md)。
真实批次结论见 [Candidate Orchestrator 报告](reports/candidate-orchestrator-live-20261116T173411Z.md)。

根目录保留与历史归档依据见 [根目录审计及整理记录](reports/root-directory-cleanup.md)。
