# Step 4：规则式 Verification Controller

> 历史阶段记录：下文状态与测试数量适用于文中日期。当前使用方式见 [项目 README](../../README.md) 和 [测试执行与修复指南](../guides/test-repair.md)。

Controller 不使用 LLM，不修改候选、不调用修复模块。它只根据已有报告给出下一步建议，保存诊断和证据。

2026-11-14 更新：Pipeline 已在 Controller 最终判定之前接入 [Docker 测试执行与修复闭环](../guides/test-repair.md)。Controller 本身仍为纯规则判定器；下文“无自动修复”的记录描述 Step 4 初版，而非当前 Pipeline 能力。

## 自动接入与离线使用

现有 `python -m independent_verification` 入口无需额外参数。`verify()` 在正常完成、阶段提前结束、异常及取消时保存 `run_result.json` 和 `decision.json`；输出目录创建前的错误仍按调用错误处理。返回值与 `run_result.json` 均包含 `controller_decision` 和 `decision_path`。原有运行状态和基础验证布尔值含义保持不变；CLI 成功还要求 Controller 没有未解决问题。

历史报告可重新判定：

```bash
python -m independent_verification --stage decide \
  --report-dir runs/archive/verification/step3-public-01 --output runs/step4-review-01
```

此模式不要求 candidate，不调用模型或执行工具，不修改历史目录，只在新目录写 `decision.json`。读取 `run_result.json`、`static_check.json` 及导出报告；完整运行必须有 `export/export.json`，离线导出使用 `export/package.json`。报告缺失、格式错误或非法评分不会得到 accept。历史 `controller_decision` 和 `basic_checks_passed` 不作为判定依据。

## 决策与归因

| 证据 | decision | 处理 |
| --- | --- | --- |
| 明确的静态检查失败 | repair | 建议 synthesis 修复，附具体错误 |
| 报告损坏、阶段异常、运行不完整或取消 | error | 保存阶段、错误及已有失败证据 |
| lint 正常执行并报告结构缺陷 | needs_review | 调查 exporter、synthesis、tests |
| Oracle 正常完成且 reward=0 | needs_review | 调查 solution、tests、environment、contract |
| Nop 正常完成且 reward=1 | needs_review | 调查 task、tests、environment、contract |
| 额外正确解法正常完成且 reward=0 | needs_review | 调查该解法、tests、environment、contract |
| 关键问题全部有明确证据且指向同一模块 | repair | 建议对应模块修复 |
| 关键问题归因不明确 | needs_review | 保留诊断，等待复核 |
| 完整检查通过且无未解决关键问题 | accept | 仅通过当前基础检查 |
| 正常停在 inspect、generate、export | not_evaluated | 不表示完整验证通过 |

读取失败的必需报告优先输出 error。明确静态失败优先于后续建议；其后执行错误、结构缺陷、Oracle/Nop/额外解法异常、关键问题依次决定主要结论。所有观察到的问题均保存在 diagnostics 中；例如 Oracle=0、Nop=1 会同时记录两个诊断。遇到 Oracle/Nop 歧义时，即使另有已归因的关键问题，也不能将整个结果交给一个模块修复。

## Python 接口与输出

`from independent_verification import decide, review_run`：

- `decide(report)` 是纯函数，不读写文件、不修改输入。report 包含 `static_check`、`package`、`run_result`，可选 `critical_issues` 和 `evidence_paths`。
- `review_run(run_dir, output, config=None)` 读取历史报告，将脱敏决策写入新的输出目录。
- `verify(..., critical_issues=())` 可接收外部提供的关键问题。这些问题同时保存在运行结果中，供离线重判使用。

关键问题格式示例：

```json
{
  "message": "人工复核确认测试要求了 Contract 未规定的输出顺序",
  "responsible_module": "tests",
  "evidence_paths": ["review/order-analysis.json"]
}
```

责任模块可选 synthesis、solution、tests、environment、contract、task、exporter、infrastructure。`responsible_module` 是调用方已完成的明确归因，Controller 不会从异常名称或 reward 猜测它；`evidence_paths` 是调用方提供的证据引用，纯函数不读取或核实引用内容。没有责任方、没有证据引用或存在多个责任方时输出 needs_review。

`decision.json` 包含：

- `decision`、`action`、`reason_code`、`reasons`。
- `responsible_module`：仅 repair 时填入明确责任模块。
- `investigate_modules`：待调查模块，不表示已确认责任。
- `diagnostics`：各项问题的 code、message、details 和待调查模块；details 保留具体检查错误、评分记录或阶段异常。
- `evidence_paths`、`task_dir`、`limitation`。

action 对应 accept、repair 或 investigate；not_evaluated 的 action 为 null。运行日志及评分报告路径保留在 evidence_paths 和诊断中。报告沿用现有脱敏规则。

CLI 对 accept、正常部分阶段返回 0；repair、needs_review、error 返回 1；取消返回 130；调用错误返回 2。

## 验证

```bash
.venv/bin/python -m unittest tests.test_controller tests.test_independent_verification -v
```

覆盖评分组合、保守归因、关键问题、缺失或非法报告、离线不执行外部工具、原报告保留、阶段提前返回、异常、取消、脱敏及 CLI 退出码。模拟 Runner 只证明控制流，不是新的真实 Harbor 或模型验收。

本次结果：新增 Controller 测试 17 项通过；与现有独立验证合跑 30 项通过、2 项跳过。完整套件 74 项通过、8 项跳过、1 项现有收集错误。历史报告离线重判：`step3-public-01` 为 accept，`step3-live-run-01` 为 error，`step3-historical-inspection` 为 not_evaluated；没有重新执行 Harbor 或模型调用。

accept 不证明测试充分性、任务难度或基准发布资格。Step 4 初版不包含自动修复、重试预算、Challenge 或 Solver。2026-11-14 已移除不再需要的 validation 残留及其失效导入测试；当前测试修复与预算由 Pipeline 管理，Challenge 和 Solver 仍未实现。
