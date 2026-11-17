# Challenge Agent 真实验收

用法、四组实验定义和当前验收状态见 [Challenge Agent 说明](../../docs/challenge-agent.md)。

```bash
python3 scripts/challenge_agent/run_acceptance.py \
  --initial-suite constructed-gap \
  --output runs/challenge-acceptance-NEW \
  --env-file /path/to/existing/.env \
  --harbor-python /path/to/harbor-venv/bin/python
```

`constructed-gap` 使用人工冻结的漏测套件：规范要求每个合法整数都正确，但初始测试只检查 `n=3`。真实 Challenge 模型自行构造错误解法及见证，真实 Test Agent 增补测试。运行 Challenge → Repair → Baseline 回放；不会生成独立初始测试，也不会预置 Challenge 错误实现。

默认最多搜索 4 个候选，可用 `--max-attempts` 调整。Repair 前建立最终 Controller 所需的审查面板：反馈组包含已确认错误候选和人工正确替代实现；保留组包含另一份人工正确实现，以及仅依据 Contract／Instruction、由独立模型对话生成并经见证审查和 Docker 验证的错误实现。保留组不进入搜索或补测反馈，只在冻结后的 Docker／Harbor 终验中评分。所有来源及调用成本保存在 `terminal-controls/`，不预置错误实现。

省略 `--initial-suite` 或指定 `generated`，沿用真实模型生成独立初始测试的四组实验及 Independent 回放。该模式不保证初始套件存在可发现的漏测。

需要真实模型、运行中的 Linux Docker、任务及 pytest 镜像和 Harbor 0.25.0。输出目录必须不存在；失败运行保留，不覆盖或标记为成功。`task-spec/` 在预检前保存可审阅的任务规范、正确对照和人工基础测试；它不是已收集、已绑定的执行套件。执行套件通过 Docker 收集后保存于 `baseline-tests/`。

`acceptance.json` 分别记录请求的后端、实际开始／完成的组别、调用次数与最终状态。预检失败时不调用模型。源码快照、脱敏轨迹、违规见证、两次评分、Controller 决策、补测差异以及 Docker／Harbor 对照保存在运行目录中。完整离线回归另行运行：

```bash
python3 -m unittest discover -s tests -v
```

代理环境的首次构造任务运行保存在 `runs/challenge-gap-acceptance-20261115-01`：Harbor 0.25.0 可用，但 Docker socket 访问被拒绝；模型调用为 0。

用户终端的后续运行 `runs/full-verification-aZhkW4Wq` 实际执行了全部 171 项测试，4 项失败；Challenge 调用了真实模型，但被审计器旧版 `expected.json` 格式误报阻止。当前已修复完整性审计中的 artifact policy 绑定、旧集成测试的对照审查记录及验收范围，并补齐终验面板；完整离线回归 173 项中 159 项通过、14 项外部测试未启用。真实复验仍待用户可访问 Docker 的终端执行，不能把离线通过当作真实闭环成功。
# 通用端到端验收

`run_e2e.py` 提供任务无关的真实发现、受限修复及三轮冻结复验；`csv_e2e.py`
只适配现有 CSV 和历史 9/24 面板。门槛、清单格式、证据和环境阻塞说明见
[端到端验收指南](../../docs/guides/challenge-e2e.md)。

