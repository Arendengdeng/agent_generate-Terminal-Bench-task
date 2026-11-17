# 工作区整理记录

本轮仅做已确认的归档、引用维护和限定缓存清理。当前分支 `master`，基准 HEAD `c8be56d`；保留整理前已有的未提交改动。未暂存、未提交、未修改 Git 历史。

## 迁移与摘要验证

| 旧路径 | 新路径 | 文件数 | SHA-256 |
|---|---|---:|---|
| `terminalbench_cli_rules/REPO_STRUCTURE.md` | `docs/REPO_STRUCTURE.md` | 1 | 全部一致 |
| `task_agnostic_audit.md` | `docs/audits/task_agnostic_audit.md` | 1 | 全部一致 |
| `task_agnostic_reaudit.md` | `docs/audits/task_agnostic_reaudit.md` | 1 | 全部一致 |
| `提交.md` | `reports/implementation-progress.md` | 1 | 全部一致 |
| `reports/audit-artifacts` | `runs/archive/audits/workspace-architecture-20261116` | 56 | 全部一致 |
| `reports/candidate-orchestrator-live-20261116T173411Z` | `runs/01_e2e_reliability/candidate-orchestrator-live-20261116T173411Z` | 841 | 全部一致 |

901 个迁移文件逐文件校验 SHA-256，全部一致；归档内部原始文件、绝对路径、历史脚本和冻结记录保持原样。28,471 个受保护文件内容校验通过（源码、测试、工具、历史运行、冻结材料、评估库、归档和嵌套仓库；排除凭证与可再生缓存）。

维护副本为 [Candidate Orchestrator 报告](candidate-orchestrator-live-20261116T173411Z.md)，其原报告随运行证据保留。当前维护报告的证据链接、根 README、文档索引和运行索引已更新。`.gitignore` 取消对共享规则、维护文档及框架测试的整体屏蔽，保留原始运行、凭证、依赖环境、缓存和嵌套仓库的忽略规则。

## 共享规则

`AGENTS.md` 已引用 `docs/REPO_STRUCTURE.md`；`CLAUDE.md` 的 `@AGENTS.md` 与 `GEMINI.md` 的 `@./AGENTS.md` 均有效。三个文件逐字保留，无需改写。

## 检查命令与结果

- 迁移前：`git status --short`、`git branch --show-current`、`git worktree list`，记录初始状态、HEAD 与 index 摘要。
- 迁移前：`rg -uuu -l -F` 搜索全部迁移路径及短引用，包含 Python、测试、配置、Markdown 和未跟踪文件；排除 Git 内部目录、依赖环境及字节码缓存。完整参数与命中文件在机器记录中。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m synthesis_agent --help`：退出码 0。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m independent_verification --help`：退出码 0。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m synthesis_agent.candidate_batch --help`：退出码 0。
- `git diff --check`：通过。
- Python 标准库逐文件 SHA-256、维护文档本地链接和未跟踪文本检查：通过；未跟踪检查不依赖 `git diff --check`。
- Git index 摘要、HEAD 与嵌套仓库状态复核：通过，未修改。

未运行单元测试、付费模型、Docker/Harbor 或完整实验；本轮不修改功能行为和测试预期。

## 删除清单

删除 73 个可再生缓存文件，共 1,359,821 字节；删除 9 个空目录（含已迁空的 `terminalbench_cli_rules/`）。

- `synthesis_agent/__pycache__`
- `synthesis_agent/candidate_batch/__pycache__`
- `independent_verification/__pycache__`
- `independent_verification/repair_proofs/__pycache__`
- `independent_verification/implementation_library/__pycache__`
- `tests/__pycache__`
- `scripts/independent_controls/__pycache__`
- `scripts/challenge_agent/__pycache__`

删除仅在迁移、入口和链接验证完成后执行。逐文件路径、大小和摘要见 [机器记录](../runs/archive/audits/workspace-cleanup-20261116T231832Z/cleanup-record.json) 中的 `deleted`。

## 保留清单

- 现有源码、接口、导入路径、CLI 参数与全部框架测试，包括原有未跟踪新增文件。
- 其他历史 `runs/`、`step3_test_1112/`、冻结源码/测试/候选、失败证据、评估库与历史压缩包。
- `real-model-e2e-worktree/` 的文件、独立 Git 历史和未提交改动；外部 worktree 不操作。
- `.harbor-venv`、本地凭证与已有环境配置；未读取或复制凭证内容。

## 未解决问题与限制

无迁移冲突或跳过项。归档内历史绝对路径、旧目录引用和重放脚本保持原样，直接运行历史脚本可能仍依赖原路径；应按本表映射定位，不把归档视为已完成实验重放。现有未提交源码改动未在本轮验证功能正确性。

逐文件迁移映射、前后摘要、受保护文件摘要、原始路径搜索结果、删除项及检查输出见 [完整机器记录](../runs/archive/audits/workspace-cleanup-20261116T231832Z/cleanup-record.json)。
