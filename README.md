# Synthesis Agent

根据 Plan 和 Contract 生成 Python 标准库 CLI 修复任务，支持独立测试、Challenge、Controller 判定、有限修复及候选批次编排。生成成功不等于独立验收通过，以 Controller 的最终结果为准。

运行要求：Python 3.11+、Linux Docker Engine、预先准备的 `python:3.11-slim` 镜像及支持工具调用的 OpenAI 兼容模型接口。完整独立验证还需要本地 `independent-verifier:pytest-9.2.0` 镜像及 Harbor。

## 安装与配置

```bash
python3 -m pip install -e .
```

按 [.env.example](.env.example) 创建本地 `.env`，填写模型及密钥，然后加载配置：

```bash
set -a
source .env
set +a
```

完整验证可复用现有 `.harbor-venv`；在新环境中，使用该环境的 Python 安装 [验证依赖](requirements-verification.txt)。运行镜像和 Harbor 须提前准备；验证命令不会自动完成环境安装。

## 运行

生成候选，输出目录必须尚不存在：

```bash
python3 -m synthesis_agent --plan examples/csv-repair/plan.json --contract examples/csv-repair/contract.json --output runs/csv-repair
```

独立验证，默认可能调用模型并启动 Docker/Harbor：

```bash
python3 -m independent_verification --candidate runs/csv-repair --output runs/csv-verification
```

批次编排：

```bash
python3 -m synthesis_agent.candidate_batch --plan examples/csv-repair/plan.json --contract examples/csv-repair/contract.json --output runs/csv-batch
```

三条命令分别也可使用安装入口 `synthesis-agent`、`independent-verification`、`candidate-orchestrator`。详细参数通过各入口的 `--help` 查看。JSONL 和 manifest 输入见 [examples/](examples/)。通用验收入口为 `python3 scripts/challenge_agent/run_e2e.py --help`；实现库工具入口为 `python3 -m independent_verification.implementation_library --help`。

## 通用诊断与修复

跨模块 `--repair` 默认使用 `execution-feedback-v1`，不要求 Contract 匹配 stdout/JSON 等证明适配器：

```bash
python3 -m independent_verification --candidate runs/candidate --output runs/02_general_repair/unique-run \
  --repair --tests runs/development-tests --acceptance-tests runs/frozen-acceptance-tests \
  --controls-manifest /path/to/independently-reviewed-controls.json --max-repairs 2
```

Agent 可读取公开输入、开发测试和分块执行证据，在无网络的全新容器中补充调查，并提出 Solution、Probe、Tests、环境或多个组件的试修。宿主核对 Requirement 引用、证据版本和组件权限；授权试修不代表已证明归因。测试调查者不能读取 Reference Solution、Synthesis Probe、冻结验收或 held-out；Synthesis 修复仅收到当前诊断、开发执行证据和授权路径。环境修改限于既有容器内的任务文件，不扩展宿主、镜像、安装器或网络权限。

调查允许多轮进行：`record_hypothesis` 保存当前假设和下一步检查，Agent 可继续读取证据、运行检查、比较或修正归因，不会因此结束分析或获得编辑权限。只有最终 `propose_repair` 才进入 Controller 授权；调查历史随诊断保存，预算不足时保留未决。

开发测试补丁若被宿主拒绝，会保留为 rejected 尝试，并将原因和有界差异返回调查；原候选和测试仍是当前版本。重调查与试修共用原预算，拒绝也计入修复次数，连续两次补丁拒绝停止自动重试。离线重判会复核拒绝记录，不能把被拒绝的补丁当作成功修复。

诊断源码读取优先使用失败 traceback 的行号：`read_source(path, start_line, end_line)` 返回带原行号和版本摘要的片段；省略范围时默认读取失败行前后各 10 行，最多 60 行。原有字符 offset 调用仍可使用，但不能与行范围混用。`list_evidence` 分页返回授权证据索引与失败位置，避免一次加载全部索引。

通用诊断按客户端实际请求字节数管理上下文，包含工具定义、Unicode 转义及服务商参数；保留既有 24,576 字节诊断上限。达到上限的 75% 时，自动将旧的完整工具调用轮次转换为确定性检查点，目标降至 60%，优先保留最近一轮；必要时仅保留有界检查点。完整 Contract 与权限说明不截断，也不调用模型生成摘要。检查点不代表归因或编辑授权。

原始执行证据不变；完整、脱敏的调查观察及工具调用保存在每次分析的 `investigations/observation-obs-*.json`，检查点另存为 `checkpoint-*.json`。模型通过 `read_observation(observation_id, offset)` 分页读取授权原始观察，空 ID 可分页列出观察 ID；工具不会打开模型指定的宿主路径。长日志、旧补丁拒绝信息和历史结果仅在模型视图中缩短，截断及后续读取引用明确标记。

预算异常保留 `BudgetExceeded` 类型并增加原因码：`context_budget_exceeded`、`model_call_budget_exceeded`、`tool_call_budget_exceeded`、`token_budget_exceeded`、`response_budget_exceeded`。最小必要上下文仍超限时，该候选停止调查并保留证据；批次可在原预算内继续，连续两次同类失败暂停。共享调用或 Token 预算耗尽仍终止批次。本地上下文整理与请求发送前的预算拒绝不计为模型调用，实际 API 尝试及重试继续共用原预算。

Self-check 与独立执行使用版本化证据 envelope：任务版本、阶段、状态、Requirement、带类型和可见范围的证据、文件变化。命令、退出码、异常、日志和文件摘要保留原有类型；证据读取只接受内存白名单 ID，不打开模型指定的宿主路径。长日志可分块读取；未执行、断言失败、执行错误和未决保持区别。

`--acceptance-tests` 指向独立生成或人工审核、绑定初始公开输入的 Test Agent 输出。验收测试在模型调用前复制并冻结，开发测试的修改不会改变它。若不指定且提供了 `--tests`，则保守地冻结该套初始测试；它本身若有错误，开发测试修复也不能绕过它。两者均未提供时，分别独立生成开发套件与验收套件后冻结。公开环境变化后仅重新绑定元数据，测试内容、节点和映射不变。

测试试修要求已确认的正确与错误对照；保留原节点、已有行为检查和 Requirement 映射，禁止 skip、xfail 和宽泛异常捕获。每次修改复跑完整开发对照并记录回归；连续两个版本出现同类失败、无修改、重复版本或预算耗尽时停止。最终冻结验收关闭所有修复，执行 Docker/Harbor 和 held-out；held-out 结果不进入后续修复。静态结构问题仍沿用既有确定性修复路径。普通 `--repair-tests`/Challenge 入口保留既有策略；新机制通过跨模块 `--repair` 使用。

`repair-history.json` 记录补丁、前后版本、未决/已解决问题、源代码摘要、Git 状态、配置、累计预算、回归及网络模式。Docker 和调查容器为无网络；当前 Harbor 导出仍为 **public 网络**，不能宣称严格无网络验收。离线 `--stage decide` 会重放诊断绑定、修改范围、开发测试补丁与冻结验收完整性。

## 通用性对照实验

使用相同初始候选、开发测试、冻结验收和已审核对照比较旧策略与通用策略，每例默认重复三次：

```bash
python3 -m independent_verification --experiment general-repair \
  --comparison-cases /path/to/frozen-cases.json \
  --output runs/02_general_repair/unique-comparison --repetitions 3
```

case 文件是 JSON 数组，每项必须包含 `id`、`task_type`、`candidate`、`tests`、`acceptance_tests`、`controls_manifest`；路径从当前工作目录解析。`id` 使用字母、数字、下划线或连字符。`controls_manifest` 使用既有独立审核格式，包含 feedback/holdout 两组正确、错误对照。`task_type` 只作报告标签，不触发诊断分支。旧策略名为 `host-contract-evidence-v1`，也可通过 `--repair-policy` 单独运行。

先以 CSV 开发机制，冻结代码与提示词，再单独评估 JSONL、manifest 和 [CLI 参数处理](examples/cli-arguments/contract.json)。迁移阶段不得边看结果边调整规则；若有改动，另建实验版本并披露任务专用逻辑。服务生命周期、非标准库依赖和宿主配置不属于首轮支持范围。

实验保存 `protocol.json`、每次运行独立输出、不可覆盖的进度记录和 `comparison.json`。输入或共享源码变化即停止，缺少模型或 Docker/Harbor 时记录 blocked，不产生成功率结论。注入 runner 的协议测试明确标记 `protocol_only`，不计为原生成功。报告使用 `experiment_id=02_general_repair` 和唯一 `run_id`，区分接受率、停止原因、修复次数、回归、调用数及可获得的 token 用量；有限对照不能证明测试充分性。

## 工作区

核心实现位于 [synthesis_agent/](synthesis_agent/) 和 [independent_verification/](independent_verification/)。保留的示例及 Challenge 脚本是现有功能依赖。协作规则见 [AGENTS.md](AGENTS.md)。

历史文档、测试、评估数据、实验、运行记录及独立仓库已移入本地 [bakcup/](bakcup/)，该目录不纳入 Git。每个归档批次的 `_migration/` 保存原路径映射、逐项校验清单、Git 状态及归档前测试日志。归档文件中的旧路径保持原样；需要重放历史实验时，应按映射恢复依赖路径。

新的运行输出继续写入 `runs/` 并由 Git 忽略。本地配置、虚拟环境及安装元数据保持原位。
