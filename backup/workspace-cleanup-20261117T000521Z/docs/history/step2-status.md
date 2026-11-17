# Step 2 完成情况说明

> 历史阶段记录：下文状态与测试数量适用于文中日期。当前使用方式见 [项目 README](../../README.md) 和 [测试执行与修复指南](../guides/test-repair.md)。

更新日期：2026-11-11。范围：最小、真正 agentic 的 Synthesis Agent。

## 当前结论

当前已实现真实的 LLM tool loop，根据已有 TaskPlan 和 Contract 构造 Python CLI repair 候选，并在独立容器副本中执行参考解法自检。生产实现没有预制业务源码、固定 bug 注入或固定答案流水线。

Step 2 状态为 **Mostly complete**：核心生成机制、工具和容器执行链路已经实现并有测试支持；当前版本多题型真实模型验收、Inventory Service Repair 场景覆盖仍未完成，不能称为整个里程碑已全部验收通过。

## 已完成的功能

| 能力 | 当前实现 | 主要位置 |
| --- | --- | --- |
| 输入 | 接收 Plan、Contract、输出目录及可选 seed；检查必要字段、依赖、路径和超时 | `inputs.py`、`agent.py:generate` |
| 使用任务要求 | 完整 Plan、Contract 和参考路径交给模型；输入在运行中不可变 | `agent.py:generate` |
| Agent loop | 多轮模型调用及 tool execution；观察回传后模型可继续修改决策和文件 | `agent.py` |
| 文件工具 | 列出、读取、写入、删除候选文件，读取只读参考材料 | `agent.py:TOOLS`、`files.py` |
| Shell 工具 | 在新建 Docker 容器中执行模型命令，返回输出和退出码 | `sandbox.py` |
| 隔离 | 无网络、非 root、只读根文件系统、无宿主 bind mount、drop capabilities | `sandbox.py:DockerSandbox` |
| 资源预算 | CPU/内存/PID/tmpfs 限制，命令超时、调用次数及文件/输出/上下文大小限制 | `config.py`、`sandbox.py`、`agent.py` |
| 初始环境 | 模型生成故障程序、配置和数据文本文件；Python 提供可信 Dockerfile | `agent.py`、`sandbox.py:dockerfile` |
| 参考解法 | 模型编写独立 `solution/solve.sh`；在副本中运行，保留原始故障文件 | `agent.py:self_check` |
| 内部自检 | 初始至少一项失败、修复后全通过；拒绝 probe error 和范围外修改 | `agent.py:self_check`、`sandbox.py:probe` |
| 完成门槛 | 自检绑定当前文件摘要，修改后旧结果失效；导出后再次核对哈希 | `agent.py` |
| 输出与轨迹 | 任务说明、环境、参考解法、构建配置、结果及模型/工具交互日志 | `agent.py`、`trace.py` |
| 输入示例 | CSV 清洗、JSONL 聚合、目录 manifest 三组 Plan/Contract | `examples/` |

表中是实现清单，不表示三个示例均已完成真实模型生成验收。

## 模型与 Python 如何分工

LLM 决定应用结构、文件内容、初始故障、样例数据、任务说明、参考解法、探针和探索命令，并根据工具反馈修改这些内容。Python 负责输入验证、工具调度、安全边界、资源限制、自检门槛和制品导出。

```text
Plan + Contract + 可选 seed
  → 输入校验、准备可信镜像、初始消息
  → LLM 选择工具并提供参数
  → Python 执行文件操作或容器命令
  → 观察结果回传 LLM
  → LLM 继续构造、调试、修改
  → self_check：初始副本失败，修复副本通过
  → finish：核对当前摘要
  → 导出 candidate 和日志
```

`shell` 每次使用新的临时容器，修改不自动持久化；模型通过 `write_file` 保存最终内容。初始容器不含参考解法，另一容器才加载并执行 solution。

## 当前支持范围

- Linux Docker 单容器，Python 标准库和基础 shell。
- CLI 数据处理修复，固定工作目录 `/app`。
- 文本候选文件和可选 UTF-8 seed。
- 不联网、不安装第三方依赖。
- 一个 Synthesis Agent 同时构造初始环境、说明、解法和内部自检。

没有实现 Planner、Controller、Challenge Agent、独立 Verifier/Test Agent、难度校准或多 Agent 协调。

## 生成的候选文件

```text
<output>/
├── plan.json
├── contract.json
├── synthesis.json
├── trace.jsonl
├── build_log.jsonl
├── self_check.json
├── checks/probe.py
└── draft/
    ├── instruction.md
    ├── environment/
    │   ├── Dockerfile
    │   └── app/...
    └── solution/
        └── solve.sh
```

`candidate_generated` 只表示候选已导出并通过生成模型自己的探针；`independent_validation=false`。失败运行也可能保存部分文件，必须检查状态。

## 验证结果与证据边界

| 层级 | 结果 | 来源与限制 |
| --- | --- | --- |
| 离线测试 | 48 项：42 通过、6 跳过，无 ResourceWarning | 本次代理实际执行；mock 测试只证明控制流 |
| 真实 Docker 集成 | 5 项全部通过，48.446 秒 | 用户终端执行并向会话提供完整输出；不是代理本地复跑通过 |
| CSV 历史候选 | 保存记录显示自检通过，manifest 全部匹配磁盘文件哈希 | `runs/v1_11.11/`；有失败后继续调试、修改解法和探针的日志 |
| 当前版本三题型真实模型生成 | 未运行 | 已提供 opt-in 测试，本次未调用付费 API |
| Inventory Service Repair | 无对应验收证据 | 没有对应 Plan/Contract、候选或服务启动测试 |
| 最终 Dockerfile build/run | 本次未验证 | 当前自检使用基础镜像和文件快照，不构建交付镜像 |

Docker 集成通过覆盖初始/修复副本自检、网络和宿主隔离、身份与只读根文件系统、超时及输出溢出清理、特殊文件拒绝、任务 assertion failure 与 probe error 分类。完整自检用的是 ScriptedClient，不能证明真实模型自主构造任务。

历史 CSV 成功记录早于新增的 `trace.jsonl` 和 `original_environment_integrity` 字段，因此不能代表当前完整版本端到端通过。具体命令和结果见 `verification.md`（历史验证记录，当前工作区已不存在）。

## 仍未完成与已知限制

1. **真实模型多样性验收。** 需要明确授权 API 消耗后运行已有三题型测试，保存当前制品与轨迹。
2. **Inventory 场景覆盖。** 当前 prompt 和输入范围限定 CLI data processing，尚不能认定支持库存服务；补齐时保持单容器、标准库范围。
3. **故意故障与偶然构建错误。** 异常分类不能自动证明初始 assertion failure 恰是 Plan 指定的挑战，仍依赖模型及具体构建证据。
4. **Contract scope 偏差。** `in_scope()` 在 `allow_additional_files=true` 时允许所有声明路径的后代，prompt 却说文件路径仍精确匹配，需要统一。
5. **交付镜像路径未验收。** 可补最小 Dockerfile build/run smoke check，无需 Harbor pipeline。
6. **共同理解错误。** 同一模型可以同时修改 probe 和 solution；自检不是独立质量保证。
7. **局部工程改进。** 两份日志存在重复；固定 900 秒容器 watchdog 与可配置 command timeout 尚未统一。

## 本版本保留的文件

| 路径 | 用途 |
| --- | --- |
| `synthesis_agent/` | 生产实现 |
| `tests/` | 离线、Docker 和可选模型验收 |
| `examples/` | 三组输入和配置示例，无预制答案 |
| `pyproject.toml` | 安装与命令入口 |
| `README.md` | 快速使用入口 |
| `Synthesis Agent 设计.md` | 当前详细协议、配置与安全边界 |
| `docs/step2-status.md` | 完成情况说明 |
| `docs/deepseek-compatibility.md` | 当前使用接口的必要兼容说明 |
| `verification.md` | 验证结果及来源 |
| `.gitignore` | 本地环境、凭据、缓存和输出排除规则 |

`.venv`、`.env`、缓存、Git/工具元数据和 `runs/` 均保留，不纳入本次删除。旧总体规划、重复讲解、迁移材料与两份完整 API 请求快照已移出项目，删除前原样备份到 `/tmp/synthesis-step2-cleanup-7kvzofgl/`，包括旧文件中的用户本地修改。该目录是临时备份，不是长期归档。

## 下一步边界

先完成当前版本真实模型验收；补齐 Inventory 构建与故障保留证据；统一 scope 并检查最终镜像构建。不需要重写架构。

本阶段不要实现 Challenge Agent、独立 Verifier、完整 Planner/Controller、难度优化循环、通用插件系统、多语言/多服务支持、评分 dashboard 或完整 Harbor pipeline。
