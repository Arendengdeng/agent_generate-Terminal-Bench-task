# 根目录审计及历史归档记录

本轮仅整理历史目录和编辑器显示；不改 Agent 行为、包结构、导入路径、CLI 参数或测试。基准分支 `master`、HEAD `c8be56d`。

## 六个目录的审计与处置

| 目录 | 文件/链接项数 | 字节 | 内容、依赖与决定 |
|---|---:|---:|---|
| `step3_test_1112/` | 5,971 | 46,173,855 | 20 轮历史实验，含冻结源码/输入/测试、33 个对照、原始日志及失败证据，无独立 Git。仍被 scripts/run_fixed_panel_acceptance.py:55、scripts/score_013144_snapshot.py:34、scripts/challenge_agent/csv_e2e.py:71 消费，未满足移动条件，原位保留。 |
| `archives/` | 9 | 42,848,226 | 仅 implementation-library-v2.1 历史代码包、原始证据包、校验清单和历史说明，无独立 Git。无运行代码依赖；维护文档链接已更新。RESULTS.json 中的旧归档路径是冻结来源字段，原样保留，以迁移表定位。 |
| `examples/` | 7 | 6,394 | 三题型可运行 Plan/Contract 和配置，无独立 Git。synthesis_agent/candidate_batch/specs.py:12、tests/helpers.py:13 及框架测试依赖这些输入，原位保留。 |
| `real-model-e2e-worktree/` | 3,552 | 57,039,693 | 独立克隆，有自己的 .git、分支与未提交源码/测试/报告；不是父仓库注册 worktree。父仓库报告含外部引用，只读保留。 |
| `.harbor-venv/` | 20,823 | 368,670,432 | Python 3.12、Harbor 及 editable 项目安装环境，含指向当前目录的安装映射和工具路径，无独立 Git。完整保留，只在 VS Code 隐藏。 |
| `synthesis_agent.egg-info/` | 5 | 1,968 | 5 个标准 setuptools 生成的安装元数据文件，无源码/实验材料/独立 Git。系统 Python 当前从此发现项目发行信息；无法完全确认人工修改来源，为保持环境不变而保留并隐藏。 |

除独立克隆外，其余目录均未发现 `.git`；普通目录本身没有独立的未提交状态。主仓库原有修改和未跟踪文件全部保留。
## 实际迁移与完整性

| 旧路径 | 新路径 | 文件数 | 总字节 | SHA-256 |
|---|---|---:|---:|---|
| `archives/implementation-library-v2.1-20261115/` | `runs/archive/legacy/implementation-library-v2.1-20261115/` | 9 | 42,848,226 | 全部一致 |

除明确维护的文档外，51,888 个原有文件/符号链接逐项校验未变，包括源码、测试、历史 runs、冻结材料、评估库数据、整个虚拟环境和嵌套仓库（含其 Git 内部文件）。未读取或复制 `.env` 凭证内容。

归档目录内部 9 个文件全部按字节保留，包含历史 README 和压缩包；不更新内部旧路径或旧链接。当前恢复与校验步骤见 [实现库指南](../docs/guides/implementation-library.md)。

## 整理前后根目录

整理前：

```text
.env
.env.example
.git/
.gitignore
.harbor-venv/
AGENTS.md
CLAUDE.md
GEMINI.md
README.md
archives/
docs/
evaluation_library/
examples/
independent_verification/
pyproject.toml
real-model-e2e-worktree/
reports/
requirements-verification.txt
runs/
scripts/
step3_test_1112/
synthesis_agent.egg-info/
synthesis_agent/
tests/
```

整理后：

```text
.env
.env.example
.git/
.gitignore
.harbor-venv/
.vscode/
AGENTS.md
CLAUDE.md
GEMINI.md
README.md
docs/
evaluation_library/
examples/
independent_verification/
pyproject.toml
real-model-e2e-worktree/
reports/
requirements-verification.txt
runs/
scripts/
step3_test_1112/
synthesis_agent.egg-info/
synthesis_agent/
tests/
```

删除了一个历史顶层目录 `archives/`；新增用户要求的 `.vscode/` 设置目录。因此普通顶层目录少一个，包含隐藏目录的总目录数不变。其他既有顶层目录未调整。

## 删除、隐藏和保留

- 仅删除迁空的 `archives/` 空目录；未删除任何文件或缓存。
- 新增 `.vscode/settings.json`，仅配置 `.harbor-venv`、`**/*.egg-info`、`**/__pycache__`、`**/.pytest_cache` 为隐藏。此前没有工作区设置，不涉及覆盖其他配置。
- 未隐藏源码、历史证据、嵌套仓库或重要未提交文件。
- `step3_test_1112/`、`examples/`、嵌套仓库、虚拟环境、egg-info 按上述原因保留。
- 明确保留的八个正式目录未移动、重命名或重构；仅维护文档及索引做相关引用调整。

## 嵌套仓库未来迁移方式

它是独立 Git 克隆，不能使用父仓库的 `git worktree move`。未来停用所有写入会话后，可将整个目录（包括 `.git`、未跟踪文件和未提交改动）普通移动至不存在的同级目标，再执行 `git -C 新路径 status --short`、`git -C 新路径 worktree list`、`git -C 新路径 remote -v` 核对。当前 `core.worktree` 未设置、没有 superproject，本地 origin 指向仍留在原位的主仓库，通常无需修改 remote。

迁移前仍需处理 reports/initial-implementation-architecture-report.md 中的维护链接及可能的外部工具绝对路径。冻结证据的历史路径应保留并另记映射。不要用 clone、reset 或 cherry-pick 替代搬运未提交文件。本轮没有执行迁移或配置变更。

## 验证命令与结果

- `git status --short`：已记录整理前后完整输出；保留原有 dirty 状态。
- `git diff --check`：通过。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m synthesis_agent --help`：0。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m independent_verification --help`：0。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m synthesis_agent.candidate_batch --help`：0。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m independent_verification.implementation_library --help`：0。
- SHA-256：全部 9 个迁移文件与受保护原文件校验通过。
- 当前维护文档本地链接检查：18 份文档、0 个失效链接；历史审计/冻结文档不改写。
- 主仓库 Git index 与 HEAD 摘要未变；嵌套仓库 Git 状态及文件摘要未变。
- 未运行单元测试、付费模型、Docker/Harbor 或完整实验；没有 git mv、git add、git commit 或历史改写。

## 剩余限制与 Git 状态说明

`step3_test_1112/` 与 `examples/` 仍有活跃依赖，不能按本轮约束迁移。嵌套仓库保持只读。egg-info 保守保留。无目标冲突或内容不明项被强行整理。

归档中原有 7 个已跟踪文件在旧路径显示未暂存删除，新位置受既有 `runs/*` 忽略规则影响；这是普通移动后的工作区状态，并非内容丢失或 Git 历史变更。本轮不改忽略规则、不暂存；后续若要将迁移纳入版本控制，需要单独处理目标路径的忽略规则并审阅暂存内容。两个压缩包仍为本地证据文件。

冻结 `evaluation_library/RESULTS.json` 和归档内部 README 仍记载旧路径；未来读取其来源位置时使用本迁移表。归档内部 README 的旧相对链接不代表当前维护入口。

逐文件旧新路径、字节数、SHA-256、全部受保护文件摘要、路径搜索参数与结果、Git 状态及检查结果见 [完整审计记录](../runs/archive/audits/root-cleanup-20261116T234755Z/audit.json)。
