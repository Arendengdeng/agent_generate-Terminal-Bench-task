# Step 1 验收报告

最终状态：**CONDITIONAL_PASS_PENDING_HUMAN_CONFIRMATION**。

按用户给出的 7 项功能和 7 个实际场景验收。不实现 Challenge，不依赖 validation 子系统。

真实模型负责语法修复、过严断言修复、遗漏补测和错误 Oracle 的分析；耗尽与回归场景使用明确标注的脚本化故障注入。所有评分来自真实 Docker/pytest，主闭环另经真实 Harbor 最终复验。

## 功能验收

|项|结果|证据|
|---|---|---|
|真实执行反馈|已验证|冻结 feedback 包含所有 node 的 phase/result、异常与断言、捕获流/命令输出、Requirement 与执行摘要；长反馈分段读取|
|正确/错误实现对照|已验证|Oracle/Nop/known_correct/known_invalid 同版测试执行；error/null 单列|
|失败归因|已验证|test_defect/implementation_defect/execution_error/uncertain；Oracle 失败不自动授权改测试|
|定向修复|已验证机制，人工确认见下|诊断引用 Contract 原文、文件/行号及本版本证据；仅 tests/fixtures 可编辑|
|有限重试|已验证|上限 2 轮；每轮重新 collect、映射、执行全部对照；旧 digest 失效|
|最终复验|已验证|Docker 收敛后的同版测试重新导出并执行 Harbor Oracle/Nop/正确/错误对照|
|结果与成本|已验证|每版测试、changes.patch、归因、node/流/结果矩阵、token 与 wall time|

## 实际场景

|场景|结果|真实模型 API 次数|证据|
|---|---|---:|---|
|语法错误与 collect 修复|passed|4|[scenario.json](<../runs/step1-acceptance-20261114/syntax/scenario.json>)|
|过严断言误拒正确实现|passed|8|[scenario.json](<../runs/step1-acceptance-20261114/overstrict/scenario.json>)|
|遗漏 Contract 要求补测|passed|10|[scenario.json](<../runs/step1-acceptance-20261114/omission/scenario.json>)|
|参考解法错误不改正确测试|passed|6|[scenario.json](<../runs/step1-acceptance-20261114-oracle-fix/oracle_error/scenario.json>)|
|依赖/Harbor 异常及 error/null 区分|passed|0|[scenario.json](<../runs/step1-acceptance-20261114/execution_error/scenario.json>)|
|两轮耗尽停止|passed|0|[scenario.json](<../runs/step1-acceptance-20261114/exhausted/scenario.json>)|
|修复引入回归被拒绝|passed|0|[scenario.json](<../runs/step1-acceptance-20261114/regression/scenario.json>)|

## 主闭环、修复历史与对照矩阵

人工构造缺陷：Contract 明确允许 JSON 键顺序与空白任意，但初版 test_double 固定比较序列化字符串。已给定正确替代解法输出字段值相同、顺序与空白不同，真实执行反证初始断言过严。真实模型读取反馈后修改断言，Contract 字节未改变。

人工确认状态：**待用户确认；模型审阅不冒充人工签署，因此正式通过条件暂为条件通过。**

完整主闭环：[run_result.json](<../runs/step1-acceptance-20261114/overstrict/verification/run_result.json>)；逐版记录：[test-loop.json](<../runs/step1-acceptance-20261114/overstrict/verification/test-loop.json>)。

验收中曾发现真实模型把错误 Oracle 误归因于测试并修改正确测试。该失败完整保留：[failure.log](<../runs/step1-acceptance-20261114/oracle_error/failure.log>)。随后增加执行层 analysis_only 禁止编辑门槛；同场景真实模型复验归因为 implementation_defect，changes.patch 为空。新源码下再次执行最终全部 Docker/Harbor 对照，没有复用历史 reward。

修正后证据：[scenario.json](<../runs/step1-acceptance-20261114-oracle-fix/oracle_error/scenario.json>)；最终新鲜复验：[run_result.json](<../runs/step1-acceptance-20261114-final/verification/run_result.json>)。

|场景/后端|测试摘要|实现|结果|预期 reward|
|---|---|---|---|---|
|regression/docker|0a18a4d144e7|oracle|fail|1|
|regression/docker|0a18a4d144e7|nop|fail|0|
|regression/docker|0a18a4d144e7|known-000|fail|1|
|regression/docker|0a18a4d144e7|invalid-000|fail|0|
|regression/docker|d8d4de3bd289|oracle|pass|1|
|regression/docker|d8d4de3bd289|nop|fail|0|
|regression/docker|d8d4de3bd289|known-000|fail|1|
|regression/docker|d8d4de3bd289|invalid-000|fail|0|
|omission/docker|b5fa1de0f025|oracle|pass|1|
|omission/docker|b5fa1de0f025|nop|fail|0|
|omission/docker|b5fa1de0f025|known-000|pass|1|
|omission/docker|b5fa1de0f025|invalid-000|fail|0|
|omission/docker|de9b104b314c|oracle|pass|1|
|omission/docker|de9b104b314c|nop|pass|0|
|omission/docker|de9b104b314c|known-000|pass|1|
|omission/docker|de9b104b314c|invalid-000|pass|0|
|overstrict/docker|569667a754e3|oracle|pass|1|
|overstrict/docker|569667a754e3|nop|fail|0|
|overstrict/docker|569667a754e3|known-000|pass|1|
|overstrict/docker|569667a754e3|invalid-000|fail|0|
|overstrict/docker|d8d4de3bd289|oracle|pass|1|
|overstrict/docker|d8d4de3bd289|nop|fail|0|
|overstrict/docker|d8d4de3bd289|known-000|fail|1|
|overstrict/docker|d8d4de3bd289|invalid-000|fail|0|
|final_recheck/docker|569667a754e3|oracle|pass|1|
|final_recheck/docker|569667a754e3|nop|fail|0|
|final_recheck/docker|569667a754e3|known-000|pass|1|
|final_recheck/docker|569667a754e3|invalid-000|fail|0|
|overstrict/harbor|最终冻结版本|oracle|pass|见原生报告|
|overstrict/harbor|最终冻结版本|nop|fail|见原生报告|
|overstrict/harbor|最终冻结版本|known-000|pass|见原生报告|
|overstrict/harbor|最终冻结版本|invalid-000|fail|见原生报告|
|final_recheck/harbor|最终冻结版本|oracle|pass|见原生报告|
|final_recheck/harbor|最终冻结版本|nop|fail|见原生报告|
|final_recheck/harbor|最终冻结版本|known-000|pass|见原生报告|
|final_recheck/harbor|最终冻结版本|invalid-000|fail|见原生报告|

遗漏补测的验收依据是同一违规实现从正常 pass 变为正常 fail，且可查最终失败 node 的实际断言；不是仅凭 Requirement-to-Test Mapping。回归与两次耗尽场景最终均不接受候选。故障场景的 error/null 不计作正常拒绝。

全部矩阵：[implementation-matrix.json](<../runs/step1-acceptance-20261114/implementation-matrix.json>)；逐断言清单（静态索引，非语义证明）：[assertion-inventory.json](<../runs/step1-acceptance-20261114/assertion-inventory.json>)。

各版修复内容保存在 attempts/*/changes.patch；分析与引用在 diagnosis.json/tests.json 中；每次 collect 的原始结果与测试快照在 collections/* 下。

## 成本、复现与限制

API 调用合计 44 次（包含首次失败及修正后复验）；已返回 token 合计 `{"prompt_tokens": 272473, "completion_tokens": 5788, "total_tokens": 278261}`；各选定场景已计时组件合计 431.742 秒，续跑进程 wall time 330.648 秒。

本组曾修正验收脚本的汇总写入冲突并续跑，已完成场景直接复用原始证据，不重复调用模型；因此单一进程覆盖整组的 wall time 不存在，记为 null。原脚本与修正后的 resume-driver 均保留。未获取的费用、CPU 和峰值内存不填写 0。

冻结源码与哈希：[source-manifest.json](<../runs/step1-acceptance-20261114/source-manifest.json>)；协议与模型配置：[protocol.json](<../runs/step1-acceptance-20261114/protocol.json>)；最终机器可读报告：[final-report.json](<../runs/step1-acceptance-20261114/final-report.json>)。

复现命令（新输出目录，真实模型会产生 API 消耗）：

```bash
.harbor-venv/bin/python scripts/accept_step1.py --output runs/step1-acceptance-NEW --real-model
```

也可只复现冻结任务的最终评分，不调用模型（输出目录必须为新目录）：

```bash
.harbor-venv/bin/python -m independent_verification --stage run \
  --candidate runs/step1-acceptance-20261114/overstrict/candidate \
  --tests runs/step1-acceptance-20261114/overstrict/verification/attempts/001/test-agent \
  --known-correct runs/step1-acceptance-20261114/overstrict/controls/correct \
  --known-invalid runs/step1-acceptance-20261114/overstrict/controls/invalid \
  --output runs/step1-frozen-replay-NEW
```

本次仅证明有限场景下执行反馈、诊断和修复机制可用。初版错误是显式注入，不能当作生成器自然缺陷率；脚本化耗尽/回归不证明真实模型发生该行为的概率。提供的错误实现标签依赖已声明见证，不自动证明任意实现违规。无 Challenge、独立留出面板或 A/B/C 对照，不能宣称评分可靠性已经提高。
