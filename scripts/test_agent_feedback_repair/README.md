# Test Agent 真实执行反馈与有限修复验收

本目录集中存放本次“真实 pytest 执行 → 反馈分析 → 有限测试修复 → 全量复验”的验收工具。

|文件|用途|
|---|---|
|`run_acceptance.py`|执行语法修复、过严断言、遗漏补测、错误 Oracle、执行异常、两轮耗尽和修复回归七个场景。|
|`build_report.py`|读取新运行的记录，生成场景报告、对照矩阵、断言索引、成本及证据哈希清单。|

从项目根目录执行新一轮验收，输出目录必须不存在；`--real-model` 会调用配置的模型 API：

```bash
.harbor-venv/bin/python scripts/test_agent_feedback_repair/run_acceptance.py \
  --output runs/test-agent-feedback-repair-acceptance-NEW --real-model
```

`--scenarios` 可指定场景子集；`--resume` 仅用于源码和配置未变化、未结束且不含失败/残缺场景目录的中断运行。复验失败场景须使用新输出目录，原证据不会覆盖。

生成新运行的报告：

```bash
.harbor-venv/bin/python scripts/test_agent_feedback_repair/build_report.py \
  --evidence runs/test-agent-feedback-repair-acceptance-NEW \
  --additional-evidence runs/test-agent-feedback-repair-oracle-recheck-NEW \
  --additional-evidence runs/test-agent-feedback-repair-final-recheck-NEW \
  --output docs/history/test-agent-feedback-repair-acceptance-NEW.md
```

报告生成器会写入证据目录，适用于新运行；归档数据按历史快照保留，不在原归档目录上重新生成报告。只有用户明确确认具体测试缺陷后，才使用 `--human-confirmed`。完整七场景验收、单场景复验和最终新鲜复验须分别如实提供，不能用脚本名称代替执行证据。

本次归档与历史结论：

- [2026-11-14 验收报告](../../docs/history/2026-11-14-test-agent-feedback-repair-acceptance.md)
- [原始证据与迁移索引](../../runs/archive/verification/2026-11-14-test-agent-feedback-repair/README.md)

## 本次命名调整

|旧名称|当前名称|
|---|---|
|`scripts/accept_step1.py`|`scripts/test_agent_feedback_repair/run_acceptance.py`|
|`scripts/report_step1.py`|`scripts/test_agent_feedback_repair/build_report.py`|
|`independent_verification/execution.py`|`independent_verification/docker_test_runner.py`|
|`independent_verification/repair_loop.py`|`independent_verification/test_repair_workflow.py`|
|`tests/test_test_repair.py`|`tests/test_test_agent_feedback_repair.py`|

生产模块保留在包内，负责 Docker 对照执行与有限反馈修复编排；测试文件按同一目的命名。冻结源码中的旧模块名称属于历史证据，保持原样。
