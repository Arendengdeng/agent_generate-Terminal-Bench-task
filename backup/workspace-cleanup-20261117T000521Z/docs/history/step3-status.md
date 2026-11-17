# Step 3：独立测试与 Harbor 基础验证

> 历史阶段记录：下文状态与测试数量适用于文中日期。当前使用方式见 [项目 README](../../README.md) 和 [测试执行与修复指南](../guides/test-repair.md)。

2026-11-12：历史 CSV 候选已在用户指定的 public 网络模式下完成真实模型测试生成、Harbor 配置/lint 与 Oracle/Nop 基础验证。Oracle=1、Nop=0；不代表测试充分性或任务难度验收。
Step 2 三题型真实模型验收是单独待办，不是本阶段开发前置条件。

## 已实现

- `CandidateTask.load`：读取成功 Synthesis 候选，限制文件路径、数量和大小，拒绝链接与特殊文件，核对 manifest，并检查未登记的 draft 文件。不会执行或采用 Synthesis 自检探针作为评分。
- `check_candidate`：检查必需文件、交付路径、可信 Synthesis Dockerfile 格式、镜像来源及明显答案泄漏。只支持现有 `/app`、标准库 Python CLI 任务，不是通用 Dockerfile 安全分析或业务语义证明。
- `TestAgent.generate`：独立模型会话，只接收 Contract、Instruction、初始环境。文件工具限定白名单，测试收集在无网络 Docker 副本中运行。输入不可修改，生成测试可修改；修改后必须重新收集。每条要求映射到实际收集的 pytest node ID。
- `export_task`：生成独立 Verifier 任务包、固定 pytest 包装器、二元评分协议和 Contract artifacts 配置。生成测试必须与候选输入及冻结文件摘要一致。离线导出不等于 lint 通过。
- Harbor 适配器：锁定 `0.25.0`，调用配置解析器、lint 和 Oracle/Nop。保存原始日志与结果，交叉核对 trial、包装器与 reward。可选其他已知正确解法只替换 solution，使用相同初始环境与测试。
- 单向编排与 CLI：没有 Challenge、Solver 或接受/修复/放弃 Controller。原 `synthesis_agent/` 未修改。

Test Agent 默认沿用已有模型配置，但使用新会话。不同 Agent 可以使用相同模型；独立性来自输入和工具权限隔离，不来自模型名称。模型仍可能理解错误、写出过弱测试或过严测试；映射和包装器不证明测试正确，也不对恶意测试代码提供反作弊保证。

## 最新 public 模式验收（2026-11-12）

按用户要求，Harbor 任务环境和独立 Verifier 默认网络模式均改为 `public`；生成阶段的 Test Agent 工具容器仍使用 Docker 原生 `--network=none`。运行前仅在 no-network 模式执行内核能力检查。结果报告与导出清单记录实际网络模式。

复用 `runs/archive/verification/step3-live-01/test-agent/` 已冻结的 15 个真实模型生成测试及全部 4 条要求映射，未再次调用模型、未修改测试或参考解法。

- 实际 Harbor 配置解析与 lint：通过，0 findings。
- Oracle：completed，reward=1。
- Nop：completed，reward=0。
- 两项 CLI 均正常退出，原生 reward、包装器报告及 reward 文件一致。
- 已知正确替代解法未提供；CSV 引号过严风险仍待复核。
- 离线回归：65 项，57 通过、8 跳过。

结果：`runs/archive/verification/step3-public-01/run_result.json`；原始日志和评分报告位于同目录的 `jobs/`；汇总：`runs/archive/verification/step3-acceptance-public-20261112.json`。

本结论仅表示此候选在 public 模式通过 Oracle/Nop 基础闭环，不证明测试没有漏洞、不过严或任务难度足够。此前 no-network 阻塞报告保留为历史证据。

## 早期 no-network 验收（2026-11-12）

总报告：`runs/archive/verification/step3-acceptance-20261112.json`。使用历史候选 `runs/archive/candidates/acceptance-csv-01`，未运行 Step 2 三题型验收。

- 固定 pytest 镜像构建成功。
- 真实 Test Agent 成功：11 次模型调用、13 次工具调用，生成 15 个测试、映射全部 4 条 Requirement。证据：`runs/archive/verification/step3-live-01/test-agent/tests.json` 与同目录轨迹。
- 历史候选任务包通过实际 Harbor 配置解析和 lint（0 findings）：`runs/archive/verification/step3-live-export-01/export/export.json`。
- 手写集成任务实际尝试 Oracle/Nop，但两次 Harbor CLI 均因 `no-network` 不受当前内核支持而失败：`runs/archive/verification/step3-harbor-160dbbb7893146d6846cbf7c74945cf9/verification/`。
- Docker daemon 内核为 `6.6.87.2-microsoft-standard-WSL2`。内核配置不包含 Harbor 0.25.0 网络隔离探测所要求的 `CONFIG_NFT_FIB_INET`。没有改为开放网络来绕过限制。
- 新增提前能力检查；历史候选正式运行入口明确记录 Docker/Harbor 可用、Harbor 网络隔离不可用，Oracle/Nop 为 `not_run`、reward=null：`runs/archive/diagnostics/step3-live-run-01/preflight.json` 和 `run_result.json`。
- 修复了手写集成测试夹具，并改为将真实集成证据保存到 `runs/step3-harbor-*`，失败时也保留。
- 静态审阅发现生成的 `test_stdlib.py` 直接比较 CSV 文本行，可能拒绝合法的不同引号形式。这是待复核的测试过严风险；没有根据参考解法修改冻结测试，测试语义质量尚未验收。

下一步是在满足 Harbor 网络隔离能力的 Docker daemon 上复用冻结测试进行 Oracle/Nop，并复核合理正确解法兼容性。不能以模型生成成功、映射完整或 lint 通过代替端到端通过。

## 早期证据

后续环境迁移：Harbor 0.25.0、pytest 9.2.0 和本项目已安装到 `.harbor-venv`；原用户级 `uv tool` Harbor 已卸载。新环境下离线套件仍为 56 通过、8 跳过。Docker 已在沙箱外确认可连接，以下 preflight 记录为迁移前的历史证据；仍未完成 Harbor 端到端验收。

历史候选 `runs/archive/candidates/acceptance-csv-01` 的 6 个 manifest 文件全部匹配。Contract、Instruction、Dockerfile、初始 CLI 和参考解法齐全，通过当前静态检查。

- 静态检查：`runs/archive/verification/step3-historical-inspection/static_check.json`。
- 实际依赖检查：`runs/archive/diagnostics/step3-historical-preflight/preflight.json`。
- 执行状态：`runs/archive/diagnostics/step3-historical-preflight/run_result.json`。
- Docker 返回 `/var/run/docker.sock` 权限不足；当前 Python 环境未安装 Harbor。
- Oracle/Nop 均为 `not_run`、`reward=null`，没有调用模型；未声称 lint、镜像构建、制品传递或 Harbor trial 成功。
- `.venv/bin/python -m unittest discover -s tests -v`：64 项，56 通过、8 跳过。新增 12 项离线测试通过，包括真实 pytest 包装器运行；新增 Harbor 集成和独立模型验收两项默认跳过。ScriptedClient 和模拟收集只证明协议与控制流。

`runs/` 是本地证据，不纳入版本控制。历史候选加载不要求 Step 2 三题型全部通过；同样也不把历史 Synthesis 成功转换为独立验证成功。

## 准备与使用

主项目仍支持 Python 3.11+。运行独立验证使用项目目录内的 `.harbor-venv`（Python 3.12+），其中安装 Harbor、pytest 和本项目。该环境已被 Git 忽略，不使用用户级 Harbor 安装。可按以下命令重建：

```bash
python3.12 -m venv .harbor-venv
.harbor-venv/bin/python -m pip install -r requirements-verification.txt
python3 -c 'from independent_verification.sandbox import base_dockerfile; print(base_dockerfile(), end="")' | docker build -t independent-verifier:pytest-9.2.0 -
```

验证入口默认选择项目 `.harbor-venv/bin/python`；`--harbor-python` 仅用于显式覆盖。交互运行可先执行 `source .harbor-venv/bin/activate`，也可以直接使用 `.harbor-venv/bin/python` 和 `.harbor-venv/bin/harbor`，无需激活。

镜像构建时安装固定 pytest；Test Agent 测试收集不联网，Harbor 任务与 Verifier 按用户要求使用 public 网络。历史候选引用的基础镜像也必须可用。CLI 不自动读取 `.env`；配置使用现有 `SYNTHESIS_MODEL`、`SYNTHESIS_API_KEY`、`SYNTHESIS_BASE_URL` 环境变量或 `--config`，密钥优先使用环境变量。

```bash
# 仅加载与静态检查，无模型、无 Docker 要求
python3 -m independent_verification --candidate runs/archive/candidates/acceptance-csv-01 --output runs/step3-inspect-new --stage inspect

# 全链路；先检查执行依赖，再调用独立模型。输出目录必须不存在。
python3 -m independent_verification --candidate runs/archive/candidates/acceptance-csv-01 --output runs/step3-new --harbor-python .harbor-venv/bin/python

# 已生成测试可以冻结复用；不再次调用模型
python3 -m independent_verification --candidate runs/archive/candidates/acceptance-csv-01 --output runs/step3-rerun --stage run --tests runs/step3-new/test-agent --harbor-python .harbor-venv/bin/python
```

`--stage generate` 只生成测试，要求 Docker 和已准备的测试镜像，Harbor 缺失不阻止此阶段。
`--stage export --tests <test-agent-output>` 可离线导出任务包；不运行 lint，`structure_valid=null`。
`--stage run` 使用已生成的测试，实际执行 lint 和 Oracle/Nop。
`--known-correct <solution-dir>` 可重复指定，目录内须有 `solve.sh`；这些解法只由 Runner 接收。

测试生成结果在 `test-agent/tests.json`，包含映射、实际 node IDs、输入/输出摘要与预算；独立模型轨迹在 `test-agent/trace.jsonl`。任务包在 `export/task/`，导出清单在 `export/package.json`；实际 lint 后才写 `export/export.json`。`run_result.json` 始终记录阶段和 Oracle/Nop 状态。

评分全部通过为 1，正常任务断言失败为 0；测试代码异常、收集失败、skip/xfail、无测试、超时或报告不一致为 error/null。CLI 对基础检查失败或执行错误返回非零。
`status=completed` 只表示运行结果完整；必须查看 `basic_checks_passed`。`independent_validation=true` / `end_to_end_validated=true` 仅在 Oracle=1、Nop=0 且所有提供的正确解法=1 时设置，范围仅为此候选的基础验证。

## 待运行验收

```bash
# 手写最小任务验证实际 Harbor 制品传递、Oracle=1/Nop=0；不调用模型
STEP3_HARBOR_TESTS=1 STEP3_HARBOR_PYTHON="$PWD/.harbor-venv/bin/python" .venv/bin/python -m unittest tests.test_independent_verification.HarborIntegrationTests -v

# 历史候选 + 真实独立模型 + Harbor；会产生 API 消耗，保存 runs/step3-model-* 证据
STEP3_MODEL_TESTS=1 STEP3_HARBOR_PYTHON="$PWD/.harbor-venv/bin/python" .venv/bin/python -m unittest tests.test_independent_verification.IndependentModelAcceptanceTests -v
```

Harbor 版本、原生结果字段和 lint 接口已按官方源码核对，但尚未在当前环境完成实际运行兼容性验证。来源：[Harbor 配置模型](https://github.com/harbor-framework/harbor/blob/main/src/harbor/models/task/config.py)、[trial 结果模型](https://github.com/harbor-framework/harbor/blob/main/src/harbor/models/trial/result.py)、[lint CLI](https://github.com/harbor-framework/harbor/blob/main/src/harbor/cli/lint.py)。运行时拒绝其他版本，不静默降级。

Oracle 通过仅说明参考解法与当前测试兼容；不代表测试无漏洞，也不代表任务有足够难度。Challenge、Solver 和完整 Controller 留待后续阶段。
