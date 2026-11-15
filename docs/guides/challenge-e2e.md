# Challenge 端到端验收

通用入口为 `scripts/challenge_agent/run_e2e.py`，Python API 为
`independent_verification.acceptance.run_acceptance(...)`。它复用生产 Challenge、
Controller、Test Agent、Docker 和 Harbor，不包含 CSV 专用提示词或预置漏洞。

```bash
.harbor-venv/bin/python scripts/challenge_agent/run_e2e.py \
  --candidate runs/task --tests runs/frozen-tests \
  --controls-manifest controls/correct-reviewed.json \
  --panel-manifest controls/historical-panel.json \
  --env-file .env --output runs/e2e-NEW
```

输出目录必须不存在。`--controls-manifest` 使用现有独立对照审查格式，但只接受
已确认的 feedback/correct，实现、Contract 和审查证据必须绑定。它们用于搜索和
修复期间保护正确行为；不向模型提供实现源码。`--panel-manifest` 单独接收历史
回归实现，不参与搜索、诊断或修复反馈：

```json
{
  "controls": [{
    "id": "example-invalid",
    "role": "invalid",
    "source": "solutions/example-invalid",
    "implementation_digest": "panel.fingerprint(load_seed(source, config).files)"
  }]
}
```

`role` 为 `correct` 或 `invalid`；`source` 相对清单目录解析，每个实现必须包含
`solve.sh`。标签和摘要需在运行前确定；标签不会被当作新完成的 Contract 审查。
历史面板已经公开，报告不声称它是新的盲测集。

## 阶段与通过条件

1. 保存任务、原测试、正确对照及审查、历史面板、源码和公开配置，预检 Docker、
   Harbor 0.25.0 和模型配置。预检不通过时不调用模型。
2. 单独准备测试健壮性：模型只选择原测试中的位置；宿主实施受限 AST 变换，
   独立模型审查后重新 collect。原版本、提议、审查、差异和新版本分别保留。
3. 真实 Challenge 自主编写违规实现。独立 Contract 见证必须拒绝该实现、接受
   Oracle 和正确对照；同一实现必须在两个新环境连续通过冻结测试，Controller
   才能授权修复。未找到漏洞保存 `not_demonstrated`，不注入人工漏洞替代发现。
4. Repair 复用发现阶段样本与证据，不重新搜索。增补测试保留原文件、fixtures
   和 node IDs，并通过通用行为审查；复验全部已确认 Challenge 违规样本及见证。
5. 冻结最终输入后，关闭模型和修复能力，默认执行三轮全新 Docker/Harbor 评分，
   每轮还重新执行独立见证。`--repeats` 可增加轮数，不能少于三轮。

准备阶段提供精确 AST 位置清单，宿主拒绝将整个 CLI 调用的结果当作文件路径复制，
并检查受支持的 fixture-root 引用是否仍未隔离。错误位置最多纠正两次，每次提议和
宿主拒绝原因都保留。独立审查确认后，可以通过 `--prepared-suite <robustness目录>`
复用整个准备版本；宿主重新验证受限变换、原始测试摘要、Contract 绑定和审查记录，
再复制到新运行内。复用准备版本不复用搜索或评分，也不把旧模型调用计成新调用。

搜索反馈包含候选自身的见证观察和评分失败位置；正确对照只返回标签、状态与 reward，
不返回参考输出。见证审查不接收候选对缺陷的自述，只审查 Contract、输入和预期断言，
并使用与执行器相同的观察操作符定义。`parsed_file` 断言使用
`path=[相对文件名, "json"|"jsonl"|"csv"]`，分别比较解析后的 JSON 值、记录列表或
二维字符串表格，避免把等价序列化强行限定为某一组文本字节。旧见证模板仍可回放。

Challenge 和 Test Agent 对明确的连接／超时传输失败最多重试两次，每次失败均消耗
共享模型调用预算并保留重试事件。HTTP 与响应协议错误不按传输失败重试；工具执行
不随模型请求重试而重放。重试耗尽仍报失败，不能被计为正常拒绝。

三轮都必须接受 Oracle 和所有正确实现，拒绝 Nop 及全部已确认 Challenge
违规实现，两个后端逐实现结果及交付产物摘要一致。全部历史面板都必须正常评分；
历史违规实现允许残余漏检，逐项列出，不向 Agent 反馈后继续修复。
异常、超时、null、缺项、重复评分、正确实现误拒、已修复漏洞重新误通过，均阻止验收。

`acceptance.json` 的 `passed` 表示上述有限闭环验收。生产 Controller 的完整
独立验收仍要求反馈和保留组各有正确及违规审查证据；本入口单独保留各轮原生判定，
不伪造审查、不放宽生产 Controller，也不把历史面板统计等同于总体稳健性。

## 健壮性准备边界

当前宿主只实施两种与任务类型无关的受限变换：

- fixture 路径表达式包入受信工作副本函数。源 fixture 保持原样，同一测试多次
  使用同一源文件得到同一副本，输入保持断言因此能看到实际被修改的工作文件。
- 在独立审查确认只解析不可信任务输出的函数外加 `UnicodeDecodeError` 守卫，
  转为明确断言。Contract 的 `output_spec` 必须明确要求 UTF-8，原函数必须已使用
  UTF-8。保留原语句和断言，其他异常不转换。

位置、Contract 引用、受限 AST 和独立审查缺一不可；模型不能提交任意修改代码。
函数内已有 try 等不支持的布局停止，不自动泛化。其他格式的未处理异常仍为执行错误，
需要增加独立的通用规则及验证，不能通过扩大 wrapper 的异常捕获范围消除错误。
生产 Challenge 阶段继续只允许新增测试，健壮性准备不占用其补测授权。

## CSV 适配与证据复核

CSV 适配脚本复用 `step3_test_1112` 的任务、9 个合法和 24 个违规实现及其历史
审查认证，默认测试为保留的 013144 冻结套件。仅适配器包含这些路径；可以通过
`--tests` 指定其他已绑定当前任务的测试版本。

```bash
.harbor-venv/bin/python scripts/challenge_agent/csv_e2e.py \
  --output runs/csv-e2e-NEW --env-file .env

.harbor-venv/bin/python scripts/challenge_agent/run_e2e.py \
  --review runs/csv-e2e-NEW/acceptance
```

现场模型默认共享 80 次模型、200 次工具预算；Challenge 最多 4 个候选、最多
2 轮修复。可通过通用入口参数调整预算或候选数；所有失败尝试均保留，终验不重置预算。
退出码：通过 0，未通过或阻塞 1，取消 130，参数错误 2。

原始输入不改写，输出包含 `original-tests/`、`robustness/`、`discovery/`、`repair/`、
`terminal-freeze.json` 和 `terminal/001` 至 `003`。各轮的 `matrix.json` 保存逐实现
结果，原始目录包含 pytest phase、断言位置、stdout/stderr、进程退出码和产物摘要。
`acceptance.json`、`report.md`、`evidence-manifest.json` 汇总状态并绑定完整证据。

离线复核不调用模型或执行器，重新校验证据清单、健壮性变换、发现归因、修复版本、
原始 Docker/Harbor 报告、完整矩阵和见证。运行目录使用绝对路径绑定，复核前不要
移动它；更新执行器源码后应使用对应运行版本复核，不能混用不同 wrapper 版本。

本环境真实入口的首次试运行 `runs/csv-e2e-20261115-01` 和早期源码版本试运行
`runs/csv-e2e-20261115-03` 均在预检被 Docker socket permission denied 阻塞，
模型调用为 0。它们保存了输入与阻塞证据，不代表真实发现或修复完成。
该阶段离线套件共 205 项，190 项通过、15 项外部集成测试未启用；新增 20 项回归全部通过。
日志、测试源码快照和离线重判保存在 `runs/challenge-e2e-validation-20261115-01`。
Docker 恢复后的真实运行与后续修正记录另行保存于 `runs/csv-e2e-live-20261115-*`，
不能将这些早期阻塞记录视为当前闭环的执行结果。

## 本次轻量验收结果

按用户后续调整，复用一次完整 Docker 回归作为完成门槛，额外 Harbor 与重复轮次停止。
`runs/csv-e2e-live-20261115-07/acceptance` 已真实自主发现候选 `008` 的误通过漏洞并完成
一轮补测：同一候选从 reward=1 变为正常拒绝 reward=0，Oracle、正确对照保持通过。
冻结测试的 37 个 Docker 对照全部正常评分；历史合法实现 9/9 通过，违规实现 21/24
被拒绝，执行异常为 0。剩余漏检为 `ascii_names_only`、`strict_email`、`strip_email_zero`。

轻量结论和修复前后证据索引保存在
`runs/challenge-e2e-live-validation-20261115-01/轻量验收.md` 与 `lightweight-acceptance.json`。
报告直接读取已有执行记录，新增模型调用为 0。原严格流程未完成，未改写为通过；
原始任务、测试、补丁、执行日志和主动停止记录均保留。
