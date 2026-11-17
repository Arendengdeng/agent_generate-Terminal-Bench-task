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

## 工作区

核心实现位于 [synthesis_agent/](synthesis_agent/) 和 [independent_verification/](independent_verification/)。保留的示例及 Challenge 脚本是现有功能依赖。协作规则见 [AGENTS.md](AGENTS.md)。

历史文档、测试、评估数据、实验、运行记录及独立仓库已移入本地 [bakcup/](bakcup/)，该目录不纳入 Git。每个归档批次的 `_migration/` 保存原路径映射、逐项校验清单、Git 状态及归档前测试日志。归档文件中的旧路径保持原样；需要重放历史实验时，应按映射恢复依赖路径。

新的运行输出继续写入 `runs/` 并由 Git 忽略。本地配置、虚拟环境及安装元数据保持原位。
