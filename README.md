# Synthesis Agent

文档入口见 [文档索引](docs/README.md)，设计规划见 [设计文档归档](docs/design/README.md)；历史任务与验证记录见 [运行记录索引](runs/README.md)。本地配置模板为 [.env.example](.env.example)，复制为 `.env` 后填写模型与密钥，并执行 `set -a; source .env; set +a` 加载到当前 shell。

根据已有 Plan、Contract 和可选参考材料，生成 Python 标准库 CLI 修复任务。所有生成代码只在受限 Linux Docker 容器内执行。成功仅表示“候选已生成并完成参考解法自检”，不代表独立验证通过。

当前功能与剩余缺口见 [Step 2 完成情况说明](docs/history/step2-status.md)。2026-11-12 离线测试 44 项通过、6 项跳过；此前用户终端真实 Docker 集成 5 项通过。

Step 3 已接入候选加载、静态检查、独立 Test Agent、Harbor 导出和 Oracle/Nop 执行入口，详见 [Step 3 使用与验证记录](docs/history/step3-status.md)。历史候选 `runs/archive/candidates/acceptance-csv-01` 已通过文件完整性与静态检查。真实 Test Agent 已生成 15 个测试并映射全部 4 条要求，导出包通过 Harbor lint。按用户要求切换 Harbor 为 public 网络后，**历史 CSV 候选已实际通过 Oracle=1、Nop=0 基础闭环验收**；测试充分性与难度仍待后续验证。

Step 2 三题型真实模型验收保持单独待办，不阻止独立验证开发。历史测试数量见各阶段记录；当前行为与验收方法见 [测试执行与修复闭环](docs/guides/test-repair.md)。

Step 3 使用项目专用 `.harbor-venv`，依赖清单为 `requirements-verification.txt`。运行前可执行 `source .harbor-venv/bin/activate`；验证入口默认使用该环境中的 Harbor，无需用户级安装。

规则式 Verification Controller 每次保存 `decision.json`，区分 `accept`、`repair`、`needs_review`、`error` 和 `not_evaluated`。Controller 的 `repair` 仍是建议；新增 Pipeline 会在最终判定前执行有界的 Test Agent 测试修复循环。接口和历史规则见 [Step 4 使用说明](docs/history/step4-status.md)。

新增显式 `--repair --max-repairs 2` 可开启跨模块 Repair Dispatcher：由 Controller 路由 Test Agent 或 Synthesis Agent，统一任务版本、修复次数和全局模型/工具调用预算。修复后重新检查，最终通过完整验证且无未决问题才可 Accept；预算耗尽保存 `needs_review`。开启该模式后，测试修复也由 Dispatcher 调度。使用方法、产物和真实验收入口见 [Repair Dispatcher](docs/repair-dispatcher.md)。

完整验证默认执行：独立生成测试 → Docker 内完整 pytest → Test Agent 诊断与测试修复（最多 2 轮）→ 全部对照重新执行 → Harbor 最终验收。诊断必须引用 Contract、当前测试位置和执行证据；歧义停止为 `needs_review`。每轮 Oracle 应通过、Nop 应失败，提供的正确替代解法也必须全部通过。修复不读取参考解法。自动测试修复还要求宿主校验 Contract 与断言的矛盾、合法和违规对照及受限补丁；仅有模型诊断或 Oracle 结果不足以授权，无法确认时保留 `needs_review`。

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

完整调用方式、隔离边界、工具协议、配置及真实验收命令见 [Synthesis Agent 设计.md](docs/design/2.%20Synthesis%20Agent%20%E8%AE%BE%E8%AE%A1.md)。Step 2 测试范围见 [完成情况说明](docs/history/step2-status.md)。

Challenge Agent 的职责边界、独立违规见证、Controller 归因门槛、运行参数与四组对照实验见 [Challenge Agent 说明](docs/challenge-agent.md)。普通 `all` 默认开启 Challenge；实验入口显式选择 `baseline/independent/challenge/repair`，不继承普通运行开关。完整真实模型闭环的验收状态以该说明和新运行证据为准。
