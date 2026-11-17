# 文档索引

所有运行命令均从项目根目录执行。当前安装和运行入口见 [项目 README](../README.md)，历史任务与执行证据见 [运行记录索引](../runs/README.md)。

| 目录 | 内容 |
|---|---|
| [design/](design/README.md) | 总体架构、早期方案、模块接口及 Synthesis 详细设计。设计目标与已实现能力需区分。 |
| guides/ | 当前功能的配置、操作和验收指南。 |
| history/ | 各阶段完成情况及当时的验收记录，保留历史结论。 |
| audits/ | 按日期保存的架构审计、问题分析及本地原始证据。 |

## 使用指南


- [测试执行与修复闭环](guides/test-repair.md)：运行方式、反馈边界、修复预算及验收证据。
- [DeepSeek 接口兼容说明](guides/deepseek-compatibility.md)：模型客户端的兼容参数和错误脱敏。

## 阶段记录

- [Step 1：真实执行反馈与有限修复验收](history/2026-11-14-test-agent-feedback-repair-acceptance.md)：真实模型、Docker/Harbor、七个场景、成本与待确认项。
- [Step 2：Synthesis Agent](history/step2-status.md)
- [Step 3：独立测试与 Harbor 基础验证](history/step3-status.md)
- [Step 4：规则式 Controller](history/step4-status.md)

阶段文档中的“当前”“未实现”和测试数量均以文中日期为准；后续操作以项目 README 和使用指南为入口。

## 审计记录

- [2026-11-13：架构与 Test Agent 审计](audits/2026-11-13/report.md)
- [2026-11-14：实现与架构审计](audits/implementation-architecture-2026-11-14.md)

审计结论保留对应时点的事实与限制。原始日志和证据 JSON 保存在审计目录中，继续作为本地材料，不纳入 Git。

## 仓库规则与补充审计

- [共享开发规则](../AGENTS.md)与[目录组织规则](REPO_STRUCTURE.md)。
- [任务无关性审计](audits/task_agnostic_audit.md)。
- [任务无关性改进复审](audits/task_agnostic_reaudit.md)。
- [工作区整理记录](../reports/workspace-cleanup.md)：迁移映射、摘要校验及保留项。

根目录审计、保留原因及最新归档映射见 [根目录整理记录](../reports/root-directory-cleanup.md)。
