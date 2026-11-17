# 01_e2e_reliability：运行失败与成本分析

- experiment_id: `01_e2e_reliability`
- run_id: `20261117T010722Z-72d855b3`
- Git HEAD: `b0c361d`；实际源码与配置保存在本次 provenance 中。
- 原始证据：`runs/01_e2e_reliability/20261117T010722Z-72d855b3`
- native_controller_decision: `error`（原始结果保留）
- experiment_result: `incomplete`

## 运行结果

Docker Desktop 启动后，Docker、两个所需镜像、Harbor 0.25.0 和模型接口预检通过。
使用固定 `deepseek-flash` 配置，完成一个候选的生成、自检和独立测试生成。
独立 Docker 测试执行出现测试自身异常，原生测试修复循环自动停止，Orchestrator
返回 `needs_review / unattributed_candidate_result`。未恢复或重启批次，未追加预算。

Challenge、实际测试修复、最终 Harbor 评分及三轮复验均未运行，不能据此评价其成功率。
无 accepted 导出；未创建 Git 提交。Harbor 预定网络模式为 public，但本次未到最终 Harbor 评分阶段。

## 失败证据与归因

生成的 `test_latest.py::test_uses_stdlib_only` 在探测子进程中使用
`print(sorted(mods))`，随后使用 `json.loads(proc.stdout.decode("utf-8"))` 解析输出。
Oracle、Nop、正确反馈控制和错误反馈控制均返回 `['json', 'sys']`，这是 Python
列表表示，包含单引号，不是合法 JSON。四个实现因此都在同一测试第 287 行出现
`JSONDecodeError`。子进程退出码为 0，证据支持该问题来自测试内部编码与解析不匹配。

证据：`batch/candidates/0001/verification/attempts/000/execution/execution.json`，
其中保存完整的 pytest 阶段结果、命令 stdout、异常类型和断言位置。
原生决策见 `batch/candidates/0001/verification/decision.json`。

Nop 和错误控制另外确实触发若干任务断言，但整套测试有执行错误，reward 均为 null。
本报告没有把这些运行记为成功拒绝。

原生 `test_repair_workflow.py` 在 execution.status 不是 `failed` 时立即以
`execution_error` 停止，未进入分析与修复。这解释了为什么虽然配置允许两次修复，
实际修复次数仍为 0。这是本次暴露出的自动闭环覆盖缺口；本次未修改框架或冻结测试。

## 版本完整性

运行期间 `AGENTS.md` 被外部修改，整份来源清单校验失败，实验入口因此记录
`source_changed_during_experiment`。冻结输入校验通过；框架 Python 源码摘要与启动时一致：
`True`。
执行失败和来源清单变化是两项独立问题，后者不覆盖原生 Controller 的 `error`。

## 成本

| 阶段 | 模型调用 | 输入 Token | 输出 Token | 总 Token | 占总 Token |
|---|---:|---:|---:|---:|---:|
| synthesis | 11 | 51880 | 4330 | 56210 | 67.1% |
| independent_test | 5 | 23553 | 4014 | 27567 | 32.9% |

合计：16 次模型调用、17 次工具调用、75,433 输入 Token、8,344 输出 Token，
共 83,777 Token。无 API 失败或重试，usage 全部已知，未知预留量为 0。
逐阶段统计与共享预算账本完全一致，调用数与三类 Token 差额均为 0。

生成阶段占 Token 约 67.1%，独立测试阶段约 32.9%；输入约占总 Token 的 90.0%。
这一个样本的主要消耗来自生成与测试上下文，不能外推 Challenge 或修复阶段的成本。
未根据未知价格推算金额。

## 后续优化依据

1. 在后续框架优化实验中，区分“可归因的测试内部异常”和基础设施错误，验证前者能否
   在 Controller 授权后进入有预算的 Test Agent 修复；继续保留原始执行错误分类。
2. 将“子进程输出序列化格式与解析方式不匹配”作为独立测试生成及通用修复的回归场景。
3. 分析生成阶段较大的累计输入上下文，评估消息裁剪或摘要；不得在本次冻结运行中更改配置。
4. 启动下次冻结实验前稳定协作文件，避免运行期间的来源清单变化。

## 验证与文件变化

`python3 -m unittest discover -s tests -v`：9 项测试通过。
本次执行命令：`python3 experiments/01_e2e_reliability/run.py`，退出码 1。
框架实现未改；实验入口只调整报告路径以遵守新的仓库命名规则。
新增本次 runs 证据、`reports/01_e2e_reliability_runs.md` 和本分析报告。
未更改 Plan/Contract、独立控制、生成测试或验收条件；未创建 Git 提交。
