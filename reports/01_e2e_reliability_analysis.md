

## 再次运行：20261117T011552Z-32760579

- experiment_id: `01_e2e_reliability`
- run_id: `20261117T011552Z-32760579`
- 完整证据：`runs/01_e2e_reliability/20261117T011552Z-32760579/`
- 使用同一 Plan/Contract、模型配置和整批预算创建新 run；保留之前运行。
- native_controller_decision: `error`
- experiment_result: `incomplete`
- Orchestrator: `needs_review / unattributed_candidate_result`
- 源码和输入完整性校验均通过。

本次再次完成候选生成、自检、独立测试生成。Docker 执行中，四个控制都在
`test_latest.py::test_input_file_not_modified` 中触发 `TypeError`：第 242 行
`check(records)` 没有传入 `tmp_path` 或已有输出，辅助函数把 None 当作路径拼接。
原生测试修复循环将其记为 execution_error 并停止；实际修复次数为 0。
原始 pytest 结果位于
`batch/candidates/0001/verification/attempts/000/execution/execution.json`。

另有三项测试质量问题，均保留原样：

- `fixtures/sample.jsonl` 实际是多行 JSON 数组，不符合 Contract 的逐行对象格式。
- 1000 条同 key 记录测试错误期待 version=1/value=v997；按输入 i%3，正确结果应为
  version=2/value=v998。Oracle 与正确控制均被该断言错误拒绝。
- 测试要求额外 CLI 参数必须返回非零，而 Contract 没有规定非法参数行为，导致正确控制
  被额外拒绝。该观察属于测试超出 Contract 范围，不作为控制实现有误的证据。

四个控制的完整套件 reward 都是 null，不能算成功拒绝。
Challenge、反馈修复、最终 Harbor 验证和三轮复验均未运行，无 accepted 导出。

| 阶段 | 模型调用 | 输入 Token | 输出 Token | 总 Token |
|---|---:|---:|---:|---:|
| synthesis | 14 | 80,031 | 7,659 | 87,690 |
| independent_test | 7 | 38,428 | 4,144 | 42,572 |
| 合计 | 21 | 118,459 | 11,803 | 130,262 |

工具调用 23 次。无 API 失败或重试；usage 全部已知，未知预留量为 0；逐阶段统计与
共享预算账本的调用数、输入、输出及总 Token 差额均为 0。
两次真实运行合计 37 次模型调用、214,039 Token（各 run 独立使用已授权预算）。

执行命令 `python3 experiments/01_e2e_reliability/run.py`，退出码 1。
本次未修改框架、输入、控制或生成测试；仅追加运行结果和分析报告。
未重新运行离线单元测试；前次 9 项测试通过的结果不视作本次端到端通过。
未创建 Git 提交。重复观察到测试内部异常无法进入现有修复循环，支持将其列为后续
通用修复机制的优先优化方向；本次没有擅自修改冻结协议来获得 accept。
