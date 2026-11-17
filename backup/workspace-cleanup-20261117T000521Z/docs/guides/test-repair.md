# 测试执行与修复闭环

2026-11-14。当前默认流程为：Test Agent 生成 → 收集并冻结 → Docker 完整执行 → 诊断 → 修改测试 → 收集并全量重跑 → Harbor 最终验收。无需旧 validation 子系统。

## 使用与兼容

```bash
python -m independent_verification --candidate runs/csv-repair --output runs/verify-01
python -m independent_verification --stage run --candidate runs/csv-repair --tests runs/old-tests --repair-tests --max-test-repairs 2 --output runs/verify-02
```

- `all` 默认启用闭环；`--no-repair-tests` 恢复单向验证。
- `run --tests` 默认不调用模型，显式 `--repair-tests` 才允许修复。既有测试目录不会修改。
- `inspect/generate/export/decide` 保留阶段语义，不启动闭环。
- `--max-test-repairs` 默认为 2，0 表示只执行 Docker 门禁而不修复。每版测试最多执行一次，重复版本停止。
- 继续支持重复 `--known-correct <solution-dir>`，目录须包含 `solve.sh`。每轮及 Harbor 均重跑全部已提供替代解法。
- 支持重复 `--known-invalid <solution-dir>`，也须包含 `solve.sh`；每轮及 Harbor 均必须得到有效 reward=0，error/null 不能当成成功拒绝。
- 修复上限固定为 0–2，不能通过参数提高至 3 轮或更多。Step 1 后续实际验收与发现的问题见 [验收报告](../history/2026-11-14-test-agent-feedback-repair-acceptance.md)。

配置沿用 `Config` 与 `SYNTHESIS_*` 环境变量。生成及修复会话共享 model/tool 调用上限；每次修复使用新消息上下文，单次上下文/文件/输出限制仍有效。Docker 套件默认上限 120 秒，参考解法执行上限 300 秒；受限容器始终在退出路径清理。预算耗尽不会获得 accept。

## 隔离与执行

Docker 执行器将初始 app 与私有 solution 放入任务容器，执行解法后仅导出 Contract 的 artifacts；Nop 不执行解法。普通文件、路径、链接、数量和字节预算均检查，支持目录 artifacts、空目录和二进制文件。

任务容器销毁后，在新 verifier 容器加载这些 artifacts、测试和 fixtures，执行完整 pytest。初始样例数据、solution、进程和临时状态不会继承。任务镜像与 verifier 镜像在本次 runner 中固定 ID；verifier 必须预装 pytest 9.2.0，不自动拉镜像或安装依赖。Docker 阶段无网络；最终 Harbor 沿用现有 public 网络配置，两阶段运行条件并非完全一致。

完成门槛是 Oracle=1、Nop=0、全部已提供正确替代解法=1，且评分有效。pytest 未预期异常保持 error/null，不因“测试报错”直接算实现失败；这类测试错误可以送诊断。容器/解法执行/制品导出/套件超时或清理失败直接停止，不修改测试。

## 诊断与修复权限

`TestAgent.generate(..., budget=...)` 可共享调用预算；新增：

```python
agent.repair(test_input, tests_output, feedback, output, budget=budget)
```

修复输入仍限于 Contract、Instruction、初始环境，另加载冻结的当前测试与受限反馈。反馈绑定 input_manifest 和 tests_digest；旧输入、旧反馈或被篡改的测试会在模型调用前拒绝。

新增工具：`read_feedback(offset)` 每次读取 4000 字符；`diagnose(...)` 引用 requirement ID、Contract 原文、测试/fixture 路径和行号、当前 evidence ID 及缺陷解释；`needs_review(reason)` 明确停止。诊断提交前禁止写入，提交后仅允许编辑 tests 和 fixtures；修改后必须重新 collect 和映射。无变化完成、重复旧版本或归因歧义均停止调查。

宿主验证引用存在且属于当前版本，不声称自动证明模型的语义解释正确。Oracle 失败不能单独证明测试错，不能仅为得到通过而放宽 Contract。反馈不提供 solution 源码或执行日志；pytest 结构化 traceback 仅列测试文件帧，不保存应用源码帧。完整原始日志独立落盘，不是模型的文件工具白名单。

Step 1 验收发现真实模型曾在错误 Oracle 场景误归因，因此新增执行层门槛：仅 Oracle 正常评分失败、其余对照均符合预期时，反馈标记 `analysis_only`。Agent 只可分析为 implementation_defect 或 uncertain；即使尝试调用 diagnose，宿主仍会拒绝编辑并停止 needs_review。其他场景仍须有 Contract、测试位置和实际证据才能开启编辑。

模型可分段读取完整结构化 pytest 反馈，包含全部 node 的 phase/result、对应 Requirement、断言异常、捕获 stdout/stderr 和 subprocess.run 的实际命令输出；原始套件流也保存。流或报告超过证据预算时不会获得有效接受。原生 Popen 等未经过 subprocess.run 的输出仅能依赖 pytest 的捕获流，不把未观测到的命令输出声称为已采集。

新增 `classify_failure` 明确记录 test_defect、implementation_defect、execution_error、uncertain；非测试归因不会开放编辑。模型 API 返回 usage 时保存 prompt/completion/total tokens 与逐请求时间，未提供则为 null。`changes.patch`、`repair-history.json`（验收汇总）和 `comparison-matrix.json` 支持逐版复核。

## 产物与最终判定

```text
test-agent/                       首次生成，保持原布局
attempts/000/execution/            第一版 Oracle/Nop/替代解法执行
attempts/001/test-agent/           feedback、diagnosis、修复测试、collection、trace
attempts/001/execution/            修改后的全部对照执行
test-loop.json                    版本链、停止原因、调用预算、最终测试目录
export/task/                      Docker 门禁通过的最终冻结版本
jobs/                             同版本 Harbor 原生结果
run_result.json / decision.json   最终判定
```

每个执行目录记录输入/测试摘要、实际镜像 ID、实现摘要、交付 artifact 摘要及逐次 pytest 报告/日志。`run_result.final_tests_output` 指向最终被执行版本。修复次数含明确拒绝修改的诊断尝试；max=2 时最多 3 版完整执行。

Docker 未通过不导出最终包，不启动 Harbor；Controller 返回 needs_review 或 error。Docker 通过后仍须通过 Harbor 配置/lint 和 Oracle/Nop/正确替代解法。Harbor 与 Docker 不一致时保留两者证据并停止，不增加无预算修复；`harbor_gate=failed_after_docker_pass` 明确标记差异。未解决关键问题同样阻止最终验证布尔值为 true。`basic_checks_passed` 仍仅表示有效 Harbor reward 组合。

历史报告离线 `--stage decide` 继续可用。旧审计报告和实验结论保留为历史状态，不改写为新闭环验收。

## 测试

```bash
PYTHONDONTWRITEBYTECODE=1 .harbor-venv/bin/python -m unittest discover -s tests -v
STEP3_DOCKER_REPAIR_TESTS=1 .harbor-venv/bin/python -m unittest tests.test_test_agent_feedback_repair.DockerRepairTests -v
STEP3_HARBOR_REPAIR_TESTS=1 .harbor-venv/bin/python -m unittest tests.test_test_agent_feedback_repair.HarborRepairTests -v
```

真实集成测试使用可信手写任务与脚本化模型，实际执行 Docker/pytest/Harbor；不调用付费模型。实际模型生成和修复效果需另行启用真实模型验收，不能用脚本化模型通过代替。

## 本次验收记录

2026-11-14 实际执行：

- 完整离线发现 99 项：87 通过、12 个真实环境/模型 opt-in 用例跳过，无错误。
- 新增真实 Docker 检查 3 项通过：一次修复后的全部对照回归；非法链接/解法失败阻断；目录、空目录及二进制 artifacts 传递。
- 原有 Docker 集成 5 项通过：自检、隔离、特殊文件、异常分类及超时/输出清理。
- 新增真实 Harbor 集成 1 项通过：首次错误测试 → 一次诊断修复 → Docker Oracle/Nop/替代解法为 1/0/1 → 同版本 Harbor 为 1/0/1 → Controller accept；历史重判同样 accept。

本地完整闭环证据：[Harbor 验收目录](../../runs/archive/verification/test-repair-harbor-6a0424623a744d3faa2021dacfed2e0c/verification)，其中 `test-loop.json`、各 attempt、最终 `run_result.json` 与 jobs 均保留。生成和修复合计 8 次脚本化模型调用，无 API 消耗。Docker 快速循环证据另见 `runs/archive/verification/test-repair-docker-bb8b88778ec5442bb51b7cd24f4ad2dc/`，边界检查在 `runs/archive/verification/test-repair-artifacts-612c75f40f154018ab78268040e9d83e/` 与 `runs/archive/verification/test-repair-binary-30333b52e9d94fe99febb6ace71c0961/`。
