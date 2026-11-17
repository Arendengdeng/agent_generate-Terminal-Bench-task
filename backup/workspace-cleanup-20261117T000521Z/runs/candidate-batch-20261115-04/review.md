# 多任务真实模型验收结果

六个不同任务方向，七次生成尝试；得到 5 个完整任务包，三类输入均覆盖。五包均通过 Harbor lint。
严格验收：接受 0，拒绝 0，未决 6。
JSONL 原任务完成 Docker/Harbor 终验且原生 Controller=accept，但四个 Challenge 见证仍待复核，故整体未接受。
实际测试修复 1 次；模型调用 295 次，工具调用 360 次（含一次有界重试）。

|任务|完整包|严格结果|阶段／模块与原因|
|---|---|---|---|
|csv-original|[任务包](packages/csv-original/task)|unresolved|Challenge 补丁审查：确认输入保护漏测，实际修复 1 次；增补补丁未通过审查，未进入终验。 [记录](tasks/csv-original/result.json)|
|csv-variant|[任务包](packages/csv-variant/task)|unresolved|Challenge 工具协议／预算：反复提交不符合 solution 写入路径约束的请求，耗尽共享模型调用预算。 [记录](tasks/csv-variant/result.json)|
|jsonl-original|[任务包](packages/jsonl-original/task)|unresolved|Challenge 见证验证／复核队列：Docker、Harbor 完整对照通过，原生 Controller=accept；4 个见证未能证明违规，严格批次验收仍为未决。 [记录](tasks/jsonl-original/result.json)|
|jsonl-variant|[任务包](packages/jsonl-variant/task)|unresolved|Test Agent 测试预期；Repair 归因能力：测试将 Unicode 服务名排序预期写反；现有修复授权仅支持 literal-stdout 规则，无法授权纠正。 [记录](tasks/jsonl-variant/result.json)|
|manifest-original|[任务包](packages/manifest-original/task)|unresolved|Challenge 工具协议／预算：反复提交非法写入路径，未完成候选评估即耗尽模型调用预算。 [记录](tasks/manifest-original/result.json)|
|manifest-variant|未生成|unresolved|Synthesis 探针生成：首次探针出现 embedded null byte；一次有界重试出现 repaired probe modified the app；两次均耗尽 40 次生成调用预算。 [记录](tasks/manifest-variant/result.json)|

## 阶段状态

|任务|Synthesis|Independent Test|Challenge|Repair|Re-verification|
|---|---|---|---|---|---|
|csv-original|passed|passed|completed|needs_review|not_run|
|csv-variant|passed|passed|error|needs_review|not_run|
|jsonl-original|passed|passed|completed|needs_review|passed|
|jsonl-variant|passed|needs_review|not_run|not_run|not_run|
|manifest-original|passed|passed|error|error|not_run|
|manifest-variant|error|not_run|not_run|not_run|not_run|

not_run 表示上游失败后未执行；error、预算耗尽、见证未确认不算成功拒绝。Repair 阶段状态包含授权与复核状态，实际编辑仅 1 次。
manifest-variant 的两次生成均失败，不计入五个完整包；两次探针与模型轨迹均已保留。

## 验证记录

- 五个任务包的文件摘要与导出清单一致；七次尝试的原始证据摘要均未变化。
- 六种对照配方真实 Docker 审查通过，见 [日志](docker-controls-regression.log)。该人工 fixture 回归不冒充真实候选生成。
- JSONL 原任务的两个后端均完成 Oracle、Nop、反馈正确／错误、保留正确／错误六项对照，正常评分一致。
- JSONL 变体测试误写排序为 `Zebra, alpha, 服务-乙, 日本`；Contract 的 Python 升序应为 `Zebra, alpha, 日本, 服务-乙`。原测试未改动。
- CSV 原任务的补丁审查理由涉及原有源码检查测试，审查范围需复核；未覆盖原审查结论或放宽验收。
- 详细阶段、成本、模块观察和终验矩阵见 [delivery-index.json](delivery-index.json)。

## 下载

- [五个任务包](candidate-packages.zip)：包含 instruction、environment、reference solution、独立测试、task.toml、Contract 和明确的未验收状态。
- [完整验证记录与源码快照](verification-records.zip)：包含首轮、重试、对照、模型轨迹、失败原因与终验记录。

本轮已获得五个完整候选包和明确的失败／未决记录；没有任务完成严格整体验收。不得将结构检查或单个后端评分解释为完整通过。
