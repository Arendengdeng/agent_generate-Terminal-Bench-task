# 项目脚本索引

- [Test Agent 真实执行反馈与有限修复验收](test_agent_feedback_repair/README.md)：七场景验收、真实模型/Docker/Harbor 执行及报告生成。

这些脚本从项目根目录执行。验收脚本是可复用工具；已完成运行的日志和冻结源码存放在 `runs/archive/`。


Repair Dispatcher 跨模块验收入口：`python3 scripts/repair_dispatcher_acceptance.py --output runs/dispatcher-new --harbor-python /path/to/harbor-venv/bin/python`。默认使用脚本模型驱动真实 Docker/Harbor；追加 `--real-model` 将诊断与修复交给配置的模型。产物、预算和未决状态说明见 [Repair Dispatcher](../docs/repair-dispatcher.md)。

- [独立正确/违规对照实验](independent_controls/README.md)：Contract 独立审查、保留组验证与结构化可靠性报告。
