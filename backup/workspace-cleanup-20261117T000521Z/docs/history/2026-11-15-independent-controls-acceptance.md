# 独立正确/违规对照验证验收

测试初始版本由脚本构造；过严断言与遗漏补测由真实模型分析和修复。评分来自真实 Docker/Harbor。

对照实现先依据 Contract 审查，并在独立容器检查数值的 11 个取值、JSONL/CSV 各 40 种记录序列的规范序列化。超时实现使用单个超时反例；源码审查另检查解析及输出表示。这些样本不穷尽所有序列化，确认不依据 Oracle reward 或待评估 pytest。

|运行|场景|实验结果|最终判定|证据充分|对照通过|后端一致性|真实模型|
|---|---|---|---|---|---|---|---|
|independent-controls-2026-11-15-05|[execution_error](../../runs/independent-controls-2026-11-15-05/execution_error/verification/run_result.json)|passed|error|True|False|consistent|False|
|independent-controls-2026-11-15-05|[overstrict](../../runs/independent-controls-2026-11-15-05/overstrict/verification/run_result.json)|passed|accept|True|True|consistent|True|
|independent-controls-2026-11-15-05|[omission](../../runs/independent-controls-2026-11-15-05/omission/verification/run_result.json)|passed|accept|True|True|consistent|True|
|independent-controls-2026-11-15-05|[timeout](../../runs/independent-controls-2026-11-15-05/timeout/verification/run_result.json)|passed|error|True|False|consistent|False|
|independent-controls-2026-11-15-05|[oracle_error](../../runs/independent-controls-2026-11-15-05/oracle_error/verification/run_result.json)|passed|needs_review|True|True|consistent|False|
|independent-controls-2026-11-15-05|[holdout_miss](../../runs/independent-controls-2026-11-15-05/holdout_miss/verification/run_result.json)|passed|needs_review|True|False|consistent|False|
|independent-controls-2026-11-15-05|[numeric](../../runs/independent-controls-2026-11-15-05/numeric/verification/run_result.json)|passed|accept|True|True|consistent|False|
|independent-controls-2026-11-15-05|[jsonl](../../runs/independent-controls-2026-11-15-05/jsonl/verification/run_result.json)|passed|accept|True|True|consistent|False|
|independent-controls-2026-11-15-05|[csv](../../runs/independent-controls-2026-11-15-05/csv/verification/run_result.json)|passed|accept|True|True|consistent|False|

## 最终冻结测试统计

按运行、测试套件、后端和对照分组分别统计，不跨后端或修复轮次累计成功率。

|运行 / 场景 / 后端|分组 / 角色|计划 / 确认|正常评分|接受 / 误拒 / 拒绝 / 漏检|error / timeout / 未执行|正常评分成功率|计划已确认样本成功比例|
|---|---|---|---|---|---|---|---|
|independent-controls-2026-11-15-05 / execution_error / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / docker|holdout / invalid|1 / 1|0|— / — / 0 / 0|1 / 0 / 0|null|0%|
|independent-controls-2026-11-15-05 / execution_error / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / execution_error / harbor|holdout / invalid|1 / 1|0|— / — / 0 / 0|1 / 0 / 0|null|0%|
|independent-controls-2026-11-15-05 / overstrict / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / overstrict / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / omission / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / docker|holdout / invalid|1 / 1|0|— / — / 0 / 0|0 / 1 / 0|null|0%|
|independent-controls-2026-11-15-05 / timeout / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / timeout / harbor|holdout / invalid|1 / 1|0|— / — / 0 / 0|0 / 1 / 0|null|0%|
|independent-controls-2026-11-15-05 / oracle_error / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / oracle_error / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / docker|holdout / invalid|1 / 1|1|— / — / 0 / 1|0 / 0 / 0|0%|0%|
|independent-controls-2026-11-15-05 / holdout_miss / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / holdout_miss / harbor|holdout / invalid|1 / 1|1|— / — / 0 / 1|0 / 0 / 0|0%|0%|
|independent-controls-2026-11-15-05 / numeric / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / numeric / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / jsonl / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / docker|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / docker|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / docker|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / docker|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / harbor|feedback / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / harbor|feedback / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / harbor|holdout / correct|1 / 1|1|1 / 0 / — / —|0 / 0 / 0|100%|100%|
|independent-controls-2026-11-15-05 / csv / harbor|holdout / invalid|1 / 1|1|— / — / 1 / 0|0 / 0 / 0|100%|100%|

## 调用成本与限制

|运行 / 场景|模型调用|工具调用|token 用量|耗时（秒）|
|---|---|---|---|---|
|independent-controls-2026-11-15-05 / execution_error|0|0|null|300.104|
|independent-controls-2026-11-15-05 / overstrict|14|17|{"prompt_tokens": 97468, "completion_tokens": 1321, "total_tokens": 98789}|409.014|
|independent-controls-2026-11-15-05 / omission|13|15|{"prompt_tokens": 76477, "completion_tokens": 1237, "total_tokens": 77714}|409.079|
|independent-controls-2026-11-15-05 / timeout|0|0|null|314.322|
|independent-controls-2026-11-15-05 / oracle_error|0|0|null|285.386|
|independent-controls-2026-11-15-05 / holdout_miss|0|0|null|283.555|
|independent-controls-2026-11-15-05 / numeric|0|0|null|286.905|
|independent-controls-2026-11-15-05 / jsonl|0|0|null|303.478|
|independent-controls-2026-11-15-05 / csv|0|0|null|335.34|

保留组只在测试冻结后执行，其失败结束本轮验收，不回传模型或触发同轮修复。

这是已确认有限对照的验收，不能推广为任意实现的正确性、测试充分性或发布就绪证明。原始运行保存源码快照、审查证据、测试摘要和执行记录；失败与复验目录独立保留。

## 证据索引

- [independent-controls-2026-11-15-05](../../runs/independent-controls-2026-11-15-05/experiments.json)：SHA-256 `bd7fe4ac1d2b8915bcc4c9f2982da33e6787a8b3d20fbbdc09db9b9b7354d034`。

## 前序运行与保留的失败

以下记录独立保留，不纳入上面的最终批次统计。初次模型改写越界、引用未支持位置或修改冻结映射均被执行层拒绝，随后改为工具调用时即时校验。另有一轮 Docker 构建缓存异常被记录为执行错误，未计作违规实现正常拒绝。

|运行|完成场景|失败场景|未完成场景|模型调用|token 用量|
|---|---|---|---|---|---|
|[independent-controls-2026-11-15-01](../../runs/independent-controls-2026-11-15-01/protocol.json)|2|jsonl|csv, execution_error, holdout_miss, omission, oracle_error, overstrict, timeout|0|0|
|[independent-controls-2026-11-15-02](../../runs/independent-controls-2026-11-15-02/protocol.json)|9|jsonl, omission, overstrict|无|27|210163|
|[independent-controls-2026-11-15-03](../../runs/independent-controls-2026-11-15-03/protocol.json)|2|omission, overstrict|无|21|140210|
|[independent-controls-2026-11-15-04](../../runs/independent-controls-2026-11-15-04/protocol.json)|2|无|无|32|219916|

## 最终复核

- 最终批次 9/9 场景符合预期：5 个完整验收通过，2 个返回 `needs_review`，2 个返回 `error`；后两类是故意构造的拒绝/执行错误场景。
- 当前源码回归：99 项，92 通过、7 按配置跳过；另外完成了独立的真实模型、Docker 和 Harbor 实验。
- 54 个 Harbor 试次均在容器存活期间记录了实际 task/verifier 镜像 ID。
- 使用当前源码重新读取原始证据，9 套最终判定与在线记录一致，评分 wrapper 未变化。后续入口防泄漏和分类边界补充由回归验证，并额外执行了真实 Docker 的 error/null 状态复验。

[最终复核与源码摘要](../../runs/independent-controls-2026-11-15-05/release-validation.json)、[回归日志](../../runs/independent-controls-2026-11-15-05/release-tests.log)、[Docker error/null 复验](../../runs/independent-controls-2026-11-15-05/docker-error-status-recheck/execution.json)。
