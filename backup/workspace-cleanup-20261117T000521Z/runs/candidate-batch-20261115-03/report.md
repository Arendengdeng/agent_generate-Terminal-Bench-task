# 六候选 CLI 修复批次

计划 6；实际生成 0；接受 0；拒绝 0；未决 6。
模型调用 0；工具调用 0。

|任务|生成|结果|失败阶段|责任模块|修复次数|记录|
|---|---|---|---|---|---:|---|
|csv-original|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/csv-original/result.json)|
|csv-variant|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/csv-variant/result.json)|
|jsonl-original|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/jsonl-original/result.json)|
|jsonl-variant|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/jsonl-variant/result.json)|
|manifest-original|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/manifest-original/result.json)|
|manifest-variant|False|unresolved / blocked|preflight|infrastructure|0|[记录](tasks/manifest-variant/result.json)|

Repair=not_needed 表示无需实际修改，仍须最终复验。执行异常、超时、null 和未执行不算成功拒绝。
未决样本不归为失败已确认；无法确定责任时记录 unknown。
