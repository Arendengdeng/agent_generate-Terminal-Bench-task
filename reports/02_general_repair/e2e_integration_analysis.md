# 完整 Task Generation Agent 集成与真实运行验收

- experiment_id: `02_general_repair`
- run_id: `e2e-20261117T061542Z-706acadd`
- 证据目录: `runs/02_general_repair/e2e-20261117T061542Z-706acadd`
运行时间: 2026-11-17T06:16:04.202510+00:00 至 2026-11-17T06:18:19.949711+00:00；总耗时 **135.747 秒**。

## 结论

本次实际从新 Plan/Contract 快照调用现有 Candidate Orchestrator，使用真实 `deepseek-flash` 完成 Synthesis、Self-check、独立开发测试生成、独立验收测试生成、Docker 开发对照验证，并进入通用多轮调查。原生 Controller 为 **needs_review**，离线重判同为 needs_review；独立验收未通过。

| 验收层级 | 本次结果 |
|---|---|
| Repair 子系统端到端成功 | **未达成**：调查触发，但未提交 Proposal、未授权或应用补丁 |
| 完整 Task Generation Agent 原生 accept | **未达成** |
| 完整可靠性验收及三轮冻结复验 | **未达成，复验未运行** |

仅执行这一次正式批次。未增加预算、恢复批次、人工修正生成测试，或手动反复尝试直至成功。没有 accepted 导出，没有创建 Git commit。此前算术 CLI 上 Repair 子系统成功的冒烟仍是单独实验，未计入本次成功结果。

## 代码与集成检查

- 分支 `master`；Git 基线 `4772077d8c896967316018efef49961de685c9d5`，带明确记录的未提交修改。
- 本次共享实现摘要 `f393d9598950ca8e25bf2fe88443ff2ad47482e08b78c34b15c0e12a240667c6`。完整文件摘要、源码归档、框架补丁、Git 状态、worktree 和公共配置在 `provenance/`。
- 初始工作区只有一个历史 backup 路径的未跟踪内容；保留未动。本次独占修改既有共享模块，没有新建 Orchestrator 或 Repair 实现，也没有移动目录。
- 检查发现原 Step 1 驱动 `repair=False`，默认 Challenge 路径走旧 test-only 流程；pipeline 原本禁止 `challenge=True` 与跨模块 `repair=True` 共用。旧 test-only 流程遇执行错误还会直接停止。
- 最小集成改动：pipeline 向既有 RepairDispatcher 转发 Challenge 和共享预算；通用 Dispatcher 在开发验证通过后，调用已有 Challenge/Docker/Harbor 最终验证入口。没有新增任务专用语义规则。
- 候选错误分类保留通用 workflow 的具体停止原因，允许已记录的候选局部失败进入下个候选；连续两个同类失败和全局预算/基础设施停止规则保留。
- 复用 Step 1 实验驱动，通过 `--protocol` 选择新配置；支持 Repair 的最终版本快照和嵌套验证目录，并记录开始/结束时间和 Repair 活动。历史协议未改。
- 通用诊断直接选择 `execution-feedback-v1`；本次 JSONL Contract 不匹配现有证明适配器（`select_adapter=None`），仍实际进入调查，证明适配器不是入口条件。
- 既有框架回归覆盖执行错误和断言失败、Solution/Probe/混合组件路由、Controller 版本与授权边界、多轮假设、同响应批量只读调查、冻结验收完整性、拒绝删除检查、held-out 隔离和补丁拒绝后再调查。框架检查不替代本次真实模型结果。

变更文件：`independent_verification/pipeline.py`、`independent_verification/repair.py`、`synthesis_agent/candidate_batch/failures.py`、`experiments/01_e2e_reliability/run.py`、`experiments/01_e2e_reliability/analysis.py`、`experiments/02_general_repair/README.md`、新增 `experiments/02_general_repair/e2e_protocol.json`、`tests/test_general_repair.py`；报告为本文件与 `reports/02_general_repair/runs.md`。

## 冻结配置与权限边界

- 输入为既有 `specs/jsonl-latest-record/`，启动时复制至全新 run 的 `inputs/`；Synthesis 没有 seed，没有使用历史生成任务。已审核 feedback/holdout 对照来自 `benchmarks/jsonl-latest-record/`，同样快照并保存逐文件哈希。
- 模型配置 `deepseek-flash`；返回的服务端模型标识未暴露，不能额外验证。API 尝试计数包含重试；本次实际没有 API 失败或重试。
- 共享上限：40 模型调用、120 工具调用、500,000 Token、10 候选；每候选最多 4 次 Challenge、最多 2 次跨组件修复。沿用 max_no_progress=8、max_self_check_failures=3。
- 诊断上下文保留既有 **24,576 字节**限制（非 Token）；诊断 completion 上限 2,000，普通 completion 上限 8,000。没有扩大这些限制。
- 开发测试与独立生成的验收测试分开；验收在诊断前冻结。开发测试可以受控修复，最终 Challenge 针对冻结验收仅允许搜索/验证，**测试修复上限为 0**；发现绕过就拒绝候选。此与历史可追加测试的 Challenge 路径不同，已在新 e2e_protocol.json/README 明示，不能将两种协议结果混为一组成功率。
- Docker 和调查容器沿用无网络隔离、资源限制；Harbor 保持 **public** 网络模式。只完成 Harbor 依赖预检，没有实际 Harbor 评分，更不能声称严格无网络 Harbor 验收。
- Test Agent 及诊断者只获得公开 Contract/Instruction/初始环境、开发测试和投影执行证据；没有 Reference Solution、Probe、冻结验收或 held-out 工具访问。Synthesis 修复仅能修改 Controller 授权组件。Challenge 使用公开输入/测试及其自行构建的违规实现/见证；宿主完成私有正确对照评分，不开放其源码。
- 本次模型调查仅使用 list_files/read_evidence/read_source；没有 run_check 补充容器、hypothesis、Proposal 或编辑。held-out 未执行、未反馈给模型。
- 正式运行期间源码与输入完整性检查均为 true；结束后再次核对冻结验收的元数据与内容摘要，完整。

输入快照 SHA-256：

- `plan.json`: `261d96d925bd226dba4394995e9ef4a0d679a9b882c0357cd39828ea4f6c6736`
- `contract.json`: `fca52904c46b4d2d4c605c6c9360bce02555d2a3364b8e1576d0a9ee0dd8f12d`
- `protocol.json`: `7548d1c0a41aeefb90ec8050e734169de432f9882f4b2af1187ccc2e132a6d0d`

## 候选与阶段结果

| 候选 | 原生 Controller | Orchestrator | 实际停止原因 |
|---|---|---|---|
| 0001 | needs_review | budget_exhausted | Test Agent context budget exceeded |

Self-check 正常执行：初始实现 R1/R4 通过、R2/R3 断言失败；应用模型生成 Solution 后 R1–R4 全部通过，符合 repair task 的初始有缺陷要求。独立开发测试生成并收集 20 个节点；独立验收测试也生成后冻结。

开发 Docker 实际评分：

| 实现 | 状态 | 预期 reward | 实际 reward | pytest 退出码 | 断言失败数 |
|---|---|---:|---:|---:|---:|
| oracle | completed | 1 | 0 | 1 | 1 |
| nop | completed | 0 | 0 | 1 | 5 |
| known-000 | completed | 1 | 0 | 1 | 1 |
| invalid-000 | completed | 0 | 0 | 1 | 6 |

全部为正常断言失败，不存在把异常/null 记为拒绝。Nop 和错误对照确实被断言拒绝，但 Oracle 与正确对照也失败，因此整套开发验证失败；这些结果不构成有效最终验收。

事后宿主证据分析：`test_latest.py::test_r3_unicode_keys_and_values` 第 226 行将去重后的输出 key 与 `sorted(r["key"] for r in records)` 比较。输入包含重复“中文”key，右侧保留重复，违反 R3“排序且无重复”；Oracle 和正确对照都输出 4 个 key，错误期望有 5 个。前一条 `data == reference(records)` 已通过。因此证据支持这是模型生成测试的缺陷，而不是 Solution 或环境缺陷。**这是事后宿主归因，不能记成 Agent 已完成诊断或修复。**

## Repair 实际参与及停止归因

执行失败进入既有通用 `prepare_feedback(policy=execution-feedback-v1)`，保存 v000 版本化 envelope、Requirement 映射、退出码、异常、命令和测试结果。实际模型轨迹：

1. 第一次响应：list_files + 读取 Oracle 对应失败证据。
2. 第二次响应：读取开发测试源码首块 + 读取正确对照的同一失败证据。
3. 第三次响应：读取源码 offset=4000 和 offset=8000 两块。
4. 准备第四次请求时，本地序列化上下文超过 24,576 字节，尚未发送第四次 API 请求。

因此，本次真实验证了**一个响应中的多个授权只读调用**与**连续三轮调查**。但没有 record_hypothesis、propose_repair、Controller 修复授权、补丁或修复后回归；不能声称自主定位成功、有效修复、多组件修复或错误归因。

具体阻塞属于 Harness 的诊断上下文管理/预算限制。源代码按固定 4,000 字符块累积到消息历史，加上工具定义、Requirement、证据索引和 JSON 转义开销，触发该限制。批次把所有 BudgetExceeded 统一记成 budget_exhausted，Repair 历史进一步记成 call_budget_exhausted；这些原始标签完整保留，但**并不是全局模型调用或总 Token 用尽**：仍有 16 次模型、90 次工具和 367,642 Token 名义余量。

根据本次“预算阻塞保留证据停止”和不在冻结运行中修改框架的规则，没有续跑其他候选。这个预算分类过粗的行为是待改进项；不将它伪装成正常候选耗尽或基础设施不可用。没有连续两个候选失败，因而未触发同类失败暂停。

基础设施均通过预检，API 成功返回全部 24 次响应；没有基础设施故障证据。模型生成了错误断言，说明测试生成存在语义缺陷；实际修复能力因 Harness 上下文阻塞而**未获充分评估**，不能直接归为模型不会修。

## Challenge、最终评分与三轮复验

| 阶段 | 状态 | 原因 |
|---|---|---|
| Challenge | not_run，0 次 | 开发检查和通用 Repair 未完成 |
| 修复后回归 | not_run | 无补丁 |
| 最终 Docker、Harbor | not_run，无评分 | 未到最终验证边界 |
| held-out | not_run | 未到最终验证边界 |
| 三轮冻结复验 | not_run，0/3 | 未获得原生 accept |

上述阶段均未用 scripted 模型代替，也未将 not_run 当作通过。开发 Docker 对照执行与最终 Docker 验收是不同阶段。

## 成本

| 阶段 | 模型调用 | 工具调用 | 输入 Token | 输出 Token | 总 Token | 阶段耗时/秒 |
|---|---:|---:|---:|---:|---:|---:|
| Synthesis（含 Self-check） | 11 | 11 | 57,132 | 4,904 | 62,036 | 57.798 |
| 独立开发测试生成 | 5 | 7 | 28,414 | 4,218 | 32,632 | 27.111 |
| 独立冻结验收生成 | 5 | 6 | 22,563 | 3,081 | 25,644 | 23.971 |
| 通用调查 | 3 | 6 | 11,749 | 297 | 12,046 | 4.775 |
| 总计 | 24 | 30 | 119,858 | 12,500 | 132,358 | 135.747（整次运行） |

主要 Token 成本来自 Synthesis 和两套独立测试生成；调查占 12,046 Token，补丁/Challenge 成本为 0。各阶段耗时与全程耗时口径不同，后者还包括预检、Docker 执行与归档。调用和 Token 对账差均为 0，unknown usage=0、未知预留=0；数值为接口报告用量，无价格或账单证据，不估算货币成本。

驱动原始统计将 acceptance-generation 标作 unattributed；本报告根据独立 trace 路径单列为验收测试生成。补充分项位于 `postrun-analysis.json`，没有改写原始 experiment-result 或 native Controller 文件。

## 与此前 JSONDecodeError 停止案例对比

历史运行 `01_e2e_reliability/20261117T010722Z-72d855b3` 的测试内部将 Python 列表 repr 当 JSON 解析，四个实现均出现 JSONDecodeError、reward=null；旧 test-only 循环在 execution_error 直接退出，没有调查。

本次通用入口不再依赖证明适配器，实际能把执行反馈送入真实多轮模型调查。框架回归 `test_execution_errors_can_enter_diagnosis` 也证明 error 分支可进入诊断，但这只是框架协议测试。**本次实际遇到的是 AssertionError，未重新复现或修复历史 JSONDecodeError，且本次连断言缺陷修复也未完成。因此不能宣称该类错误已在完整 Agent 中闭环解决。** 不同源码、配置和阶段的历史结果未与本次合并计算成功率。

## 检查、复现与下一步

- 正式运行前 `python3 -m unittest discover -s tests -v`：42 项，41 通过、1 项 opt-in Docker/Harbor smoke 跳过；日志在 `provenance/task-generation-regression-final.log`。该跳过的子系统 smoke 不影响本次另行启动的真实完整流水线。
- 驱动时间元数据修改后 `python3 -m unittest tests.test_e2e_reliability -v`：9 项通过；日志在 `provenance/task-generation-driver-regression.log`。
- `git diff --check` 通过。Docker Linux、两个本地镜像、Harbor 0.25.0、模型 `/models` 预检全部通过，详情在 `preflight/environment.json`。
- 结束后离线 `review_run` 得到 needs_review，冻结验收完整性检查通过；证据位于 `postrun-review/` 和 `postrun-analysis.json`。这些检查没有调用模型或修改原始结果。

复现入口（必须替换为新的唯一 run ID，旧结果不可覆盖）：

```bash
python3 experiments/01_e2e_reliability/run.py \
  --protocol experiments/02_general_repair/e2e_protocol.json \
  --run-id NEW_UNIQUE_RUN_ID
```

下一步优先修复通用诊断的上下文管理：按预算分页证据索引，提供按失败行定位的源码片段，以及受限历史压缩/检查点，保持同样 24,576 字节限制并保留完整原始调查记录。应增加“批量读取后仍可提交 Proposal”的回归；区分上下文预算、completion、总调用与总 Token 停止原因，避免局部上下文满直接伪装成全局调用耗尽。不要引入 JSONL 专用语义规则，也不要靠扩大预算掩盖问题。

这需要另一次代码修改、回归、冻结和全新 run_id。本次按预算停止规则归档，未在失败后修改框架或追加正式运行。最终 Challenge 的零编辑冻结边界也仍需后续真实可达运行验证；本次不能凭新增调用链测试宣布它已完成端到端验收。

## 运行结束后的上下文管理修复

以下修改发生在上述冻结运行结束之后，不属于 run_id `e2e-20261117T061542Z-706acadd` 使用的源码版本，也没有据此改写其 needs_review 结果。

- 复用现有通用诊断，增加按失败行号读取的有界源码片段、分页证据索引和完整观察 ID 读取；保留原 offset 调用兼容性及权限白名单。
- 按实际传输请求字节计算上下文，达到 75% 时将旧的完整工具轮次转换为确定性检查点，目标为 60%，优先保留最近一轮。完整 Contract 与权限说明不截断；不调用模型生成摘要。
- 原始执行证据不变，完整、脱敏的调查观察、原始工具调用和检查点分别归档。长日志及旧补丁拒绝信息只在模型视图中缩短，支持分页取回。
- BudgetExceeded 保留兼容类型并携带稳定原因码，区分 context、模型调用、工具调用、总 Token 与响应大小。原因贯穿 Agent、RepairDispatcher 和 Orchestrator；上下文失败允许继续下一候选，连续同类失败暂停，全局预算耗尽仍终止批次。
- 请求发送前的上下文或预算拒绝不增加模型调用计数。现有 24,576 字节诊断限制及 40/120/500,000 总预算均未扩大，没有新增任务专用语义规则。

修改文件：`README.md`、`independent_verification/agent.py`、`independent_verification/diagnosis.py`、`independent_verification/repair.py`、`synthesis_agent/agent.py`、`synthesis_agent/client.py`、`synthesis_agent/errors.py`、`synthesis_agent/candidate_batch/failures.py`、`synthesis_agent/candidate_batch/orchestrator.py`、`tests/test_general_repair.py`。

修复后的框架检查：`python3 -m unittest discover -s tests -v`，54 项，53 通过、1 项 opt-in 容器冒烟跳过；`git diff --check` 通过。新增回归在第 706 行的长源码和长 Unicode 日志上完成 14 轮双工具读取，经检查点后仍可提交 Proposal，逐次请求均不超过原诊断上下文上限；并验证原始观察可完整取回、非法路径拒绝、无效工具调用恢复及预算原因与批次停止行为。

这些是脚本模型参与的框架回归，不是新的实时模型能力证据。修复后未再执行付费端到端实验，完整 Agent 原生 accept、历史 JSONDecodeError 的实时修复和三轮冻结复验仍未验证。本节记录修复与回归；此前“没有创建 commit”描述的是冻结实验结束时的状态，后续按用户要求提交发现与代码。
