# Repair Dispatcher

开启跨模块闭环：

```bash
python3 -m independent_verification --candidate runs/candidate --output runs/repair-new \
  --stage all --repair --max-repairs 2 --harbor-python /path/to/harbor-venv/bin/python
```

可用 `--tests` 提供已冻结且绑定当前候选输入的测试。`--repair` 仅支持 `all/run`，不能与 `--repair-tests/--no-repair-tests` 组合。未开启时保持原入口，包括 `all` 的测试专用循环；测试专用循环同样要求宿主归因校验和合法/违规对照。Python API 为 `verify(..., repair=True, max_repairs=2)` 或 `RepairDispatcher.run(...)`。输出目录必须不存在。

## 决策与预算

Controller 保持纯规则决策，Dispatcher 执行路由：`tests` 交给 Test Agent；`synthesis/solution/environment/task` 交给 Synthesis Agent。Contract、导出器、基础设施、多模块混合归因和单纯 Oracle 失败保留未决，不推测责任方。

执行发现测试异常后，Test Agent 先以只读模式诊断，引用 Requirement、Contract 原文、测试行号和当前执行证据。这份模型诊断只是提议，不能作为已确认归因。宿主必须依据冻结的 Contract、测试 AST、映射和失败位置验证矛盾，保存 `attribution.json` 后，Controller 才能授权编辑；`needs_review` 永不升级为修复。分析和编辑共用调用预算。Test Agent 只接收公开输入、测试和执行反馈投影，不接收参考解法或私有 probe。当前自动校验规则仅支持明确的整数字面量 stdout 约定：Requirement 为 `Print <整数> and exit successfully.`、`output_spec` 为 `<同一整数> followed by newline.`、无输入，测试直接调用 Contract CLI 并断言 stdout 等于常量。期望值只从 Contract 得出；规则不解析 Oracle 输出作为真值。其他语言、复杂断言或缺少匹配证据时保留 `needs_review`，没有通用语义归因能力。

`max_repairs` 默认 2；所有模块的失败尝试也计数。`Config.max_model_calls/max_tool_calls` 是整个闭环累计上限，包含初次生成、分析与修复。调用前检查，失败调用也计费。每次 Agent 仍受上下文、文件和容器超时限制；token 用量仅在接口提供时记录，没有费用或 token 上限。

次数或调用预算耗尽、重复版本、无修改、未决问题均禁止 Accept，保存 `needs_review` 并返回退出码 1；基础设施错误返回 1，取消返回 130。最后一次允许的修复仍须复验，预算恰好用完但完整验证通过时可以 Accept。部分阶段不会触发跨模块修复。

## 版本与复验

`versions/v000` 是输入快照。每次有效修复递增任务版本，记录父版本、候选 manifest、公开输入 manifest 和测试 digest。仅测试变化也创建新版本；未变化的候选可引用上一版本快照。Synthesis 修复冻结 Contract 和已有 Plan；旧候选缺少 Plan 时建立仅用于修复的兼容 Plan。

Synthesis 在受限范围内修改并完成当前版本自检。公开输入变化后重新生成独立测试；仅参考解法变化可复用测试。测试修复前必须提供至少一个已知合法实现和一个单独的已知违规实现；Nop 不替代违规实现。Dispatcher 将对照实现冻结到自身目录。宿主还要求被引用断言在合法对照上确实失败。

修复必须重新 collect，保持原节点和 Requirement 映射。当前规则只允许纠正被确认断言的常量，其余 AST、测试和 fixtures 必须保留；删除断言、skip、宽泛异常捕获或其他顺带改动均拒绝。随后从干净容器执行整个测试集，要求所有合法实现通过、所有违规实现正常断言失败；error/null 不算成功拒绝。有限对照不是测试充分性的证明。

自动发现的静态问题由新静态检查消解，测试诊断由当前版本的完整 Docker 对照执行消解。外部传入的 `critical_issues` 没有通用可执行的消解协议，因此只提供 `responsible_module` 和 `evidence_paths` 字符串不足以授权，Dispatcher 直接保留未决，不修改任何模块；不会因为 Agent 声称修复而自动清除。

Accept 要求当前版本的 Docker 检查、最终静态检查、导出/lint、Harbor Oracle=1、Nop=0、所有正确对照=1、错误对照=0，且没有未决问题。最终 Harbor 验证关闭所有修复能力。

根目录保存 `repair-history.json`、`run_result.json` 和 `decision.json`。每次修复在 `repairs/NNN` 保存请求、响应、预算和 `changes.patch`；各版本保存静态检查、执行反馈、分析和验证报告。历史记录分别列出已解决与未解决问题及复验证据。离线 `--stage decide` 重新计算 Contract/AST 归因和补丁校验，检查冻结对照及历史与摘要一致、最终验证摘要、候选及测试绑定，不能将未完成闭环重判为 Accept。

## 回归与真实验收

```bash
python3 -m unittest discover -s tests -v
REPAIR_DISPATCHER_INTEGRATION=1 HARBOR_PYTHON=/path/to/harbor-venv/bin/python \
  python3 -m unittest tests.test_repair_dispatcher.RealDispatcherTests -v
```

集成测试故意注入“R1 要求 42，测试却期待 43”的缺陷，使用脚本模型驱动真实 Docker、独立 Verifier 和 Harbor，验证发现、诊断、授权、修改、重新执行及离线重判，并将产物保留在 `runs/repair-dispatcher-*`。该测试验证执行链路，不是实时模型的修复能力验收。

实时模型验收入口：

```bash
python3 scripts/repair_dispatcher_acceptance.py --output runs/dispatcher-live-new \
  --harbor-python /path/to/harbor-venv/bin/python --real-model
```

入口先注入错误测试，然后将诊断及修复交给配置的模型；配置使用 `SYNTHESIS_MODEL/SYNTHESIS_API_KEY/SYNTHESIS_BASE_URL` 环境变量或 `--config` JSON。未配置模型时，保存 `acceptance.json` 并标记 `blocked`，不会声称通过。去掉 `--real-model` 可复现脚本模型的真实容器验收。

## 首轮验证记录（2026-11-14，收紧归因前）

- 本地套件：72 项，64 通过，8 项需显式开启的集成测试跳过；另行执行的原项目 Synthesis 生成回归 16 项通过。
- 真实容器验收：`runs/dispatcher-acceptance-validated/acceptance.json` 为 `passed`。脚本模型完成 1 次测试修复，累计 7 次模型调用、7 次工具调用。
- Docker 对照由 `[Oracle=0, Nop=0, known-correct=0]` 变为 `[1, 0, 1]`；最终 Harbor 同为 `[1, 0, 1]`，离线重判为 `accept`。请求、响应、patch、版本和检查记录位于 `runs/dispatcher-acceptance-validated/verification/`。
- 实时模型验收尚未完成：当前进程没有 `SYNTHESIS_MODEL` 配置，`runs/dispatcher-acceptance-live/acceptance.json` 保存 `blocked`，没有调用实时模型。

## 归因与反过拟合加固

首轮验收没有单独的违规实现，且宿主只检查模型诊断的引用形式，不能据此证明语义归因。加固后的验收使用输出 42 的合法对照、输出 43 的违规对照，以及独立的 Nop。完整证据已保存至 `runs/dispatcher-evidence-controls/`，包含宿主归因、补丁 AST 校验、冻结对照、前后 Docker 评分和最终 Harbor 评分。

加固后本地套件 79 项：71 通过、8 项按开关跳过。真实 Docker/Harbor（脚本模型）验收通过，1 次修复，7 次模型调用、7 次工具调用：

| 阶段 | Oracle | Nop | 合法对照 | 违规对照 |
| --- | --- | --- | --- | --- |
| 修复前 Docker | 0 | 0 | 0 | 1 |
| 修复后 Docker | 1 | 0 | 1 | 0 |
| 最终 Harbor | 1 | 0 | 1 | 0 |

离线重判重新核验 Contract/AST 归因、补丁和冻结对照后为 `accept`。这说明本例修复纠正了错误拒绝并恢复了对违规实现的拒绝；有限对照不能证明一般测试充分性或模型自主语义归因能力。
