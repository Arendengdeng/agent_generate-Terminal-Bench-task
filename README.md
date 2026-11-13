# Synthesis Agent

根据已有 Plan、Contract 和可选参考材料，生成 Python 标准库 CLI 修复任务。所有生成代码只在受限 Linux Docker 容器内执行。成功仅表示“候选已生成并完成参考解法自检”，不代表独立验证通过。

当前功能与剩余缺口见 [Step 2 完成情况说明](docs/step2-status.md)。2026-11-12 离线测试 44 项通过、6 项跳过；此前用户终端真实 Docker 集成 5 项通过。

Step 3 已接入候选加载、静态检查、独立 Test Agent、Harbor 导出和 Oracle/Nop 执行入口，详见 [Step 3 使用与验证记录](docs/step3-status.md)。历史候选 `runs/acceptance-csv-01` 已通过文件完整性与静态检查。真实 Test Agent 已生成 15 个测试并映射全部 4 条要求，导出包通过 Harbor lint。按用户要求切换 Harbor 为 public 网络后，**历史 CSV 候选已实际通过 Oracle=1、Nop=0 基础闭环验收**；测试充分性与难度仍待后续验证。

Step 2 三题型真实模型验收保持单独待办，不阻止 Step 3 开发。当前完整离线套件 57 项通过、8 项跳过。

Step 3 使用项目专用 `.harbor-venv`，依赖清单为 `requirements-verification.txt`。运行前可执行 `source .harbor-venv/bin/activate`；验证入口默认使用该环境中的 Harbor，无需用户级安装。

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

完整调用方式、隔离边界、工具协议、配置及真实验收命令见 [Synthesis Agent 设计.md](2.%20Synthesis%20Agent%20设计.md)。Step 2 测试范围见 [完成情况说明](docs/step2-status.md)。
