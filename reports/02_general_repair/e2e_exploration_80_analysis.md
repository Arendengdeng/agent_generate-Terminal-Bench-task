# 80 次调用探索性 E2E：结果与阶段成本

- experiment_id: `02_general_repair`
- run_id: `explore80-20261117T170350Z-77905313`
- variant: `exploratory_80_calls`
- 原始证据：`runs/02_general_repair/explore80-20261117T170350Z-77905313`
- Git 基线：`042bf3b7d43a463593ca014c640c3324de14749c`，带运行前已记录的提示与成本观测修改；未创建新 commit。
- framework_code_version: `28740f1f1e27cadf11eb570878227ce6b70d4601ce8beb4b1bf6cfbe403040f8`
- 时间：2026-11-17T17:03:50.319923+00:00 至 2026-11-17T17:07:32.485329+00:00，耗时 **222.165 秒**。

## 实际结果与结论边界

已实际执行一次真实 deepseek-flash 探索批次，生成了 3 个候选，执行 9 轮 Self-check。所有候选均未通过自检；候选 0002、0003 连续出现 self_check_failure，触发原协议的 **paused_repeated_failure / repeated_failure**。实验结果为 **incomplete**。

**没有耗尽预算，也没有阶段预留。** 实际消耗 45/80 次模型调用、51/240 次 Agent 工具调用、370,599/1,000,000 个接口报告 Token。剩余 35 次模型调用、189 次工具调用和 629,401 Token 未使用，停止原因是原有重复质量失败保护，不能标为预算不足。没有人工续跑、重试直至成功或改冻结代码。

| 验收层级 | 本次结果 |
|---|---|
| Repair 子系统端到端成功 | 未验证：未进入跨模块 RepairDispatcher |
| 完整 Task Generation Agent 原生 accept | 未获得；原生验收 Controller **not_run / null**，不是 needs_review |
| 三轮冻结复验的完整可靠性验收 | 未运行，0/3 |

本轮观测到的是 Synthesis 与自检的实际成本，**没有得到完整流程的全部阶段成本**。独立测试、通用 Diagnosis/Repair、Challenge 和最终评分未到达；它们的 0 次调用表示 not_run，不代表实际完成成本为 0。不能用这些数据证明 80 次调用足够，也不能据此推导应预留多少调用。

## 条件与运行前修改

- 新协议为 `experiments/02_general_repair/e2e_exploration_protocol.json`：整批共享 80 次模型调用、240 次工具调用和 1,000,000 Token，无阶段限额或预留。历史 40 次协议保持不变。
- 沿用 JSONL Plan/Contract，启动时建立全新输入与审核控制快照；没有 seed，没有复用历史生成任务。最多 10 个候选、每候选最多 2 次 Repair、4 次 Challenge，max_no_progress=8、max_self_check_failures=3，原生验收条件未改。
- 模型沿用本地配置 `deepseek-flash`。接口未暴露可用于核验的返回模型标识。全部 45 次 API 尝试成功，无传输重试、未知用量或未知 Token 预留；不估算无价格依据的货币成本。
- 同时加强通用提示：Probe 结构比较必须保持一致；自检失败同时考虑 Probe、fixture、实现和环境；shell 修改不持久；测试不得添加 CLI 缺参时可安全 import 等 Contract 外要求。未增加 JSONL/CSV 语义适配规则，没有删验证、放宽断言或加入草稿移交机制。
- 增加 trace phase、源文件摘要变化及工具计费观测；成本分析区分独立验收生成、诊断、组件修复与 Challenge 阶段。报告预算和复现命令读取实际协议，不再硬编码 40 次。观测不改变预算或决策。
- Docker Linux、两个本地镜像、Harbor 0.25.0、模型 API 预检均通过。Self-check 在实际 Docker 容器执行；Docker 沿用无网络隔离。Harbor 保持 **public** 预定网络模式，但本次没有 Harbor 评分，不能宣称完成 Harbor 验收。
- 源码、提示、配置、输入哈希及 Git dirty 状态均保存于 provenance/、inputs/；原生结束与事后核对的源码/输入完整性均为 true。held-out 未运行，也未反馈给模型。

## 每个候选的失败与归因

| 候选 | 模型调用 | 工具调用 | 总 Token | 自检顺序 | 停止类别 |
|---|---:|---:|---:|---|---|
| 0001 | 14 | 14 | 98,462 | error, error, error | probe_defect |
| 0002 | 11 | 16 | 99,474 | error, failed, failed | self_check_failure |
| 0003 | 20 | 21 | 172,663 | failed, failed, failed | self_check_failure |

### 0001：Probe 内部数据结构使用不一致，归因未纠正

三轮自检中，初始及修复后的 R2/R3/R4 均出现 `TypeError: tuple indices must be integers or slices, not str`；Solution 执行退出码为 0。最终 Probe 的 `_expected` 将 best[key] 保存为 tuple，随后却通过 cur["version"] 读取，足以解释异常。模型修改了 Probe 的归一化与注释，甚至把异常归因于 check 名称遮蔽，但仍保留该 tuple/dict 混用。它没有成功修正真实错误。以上为事后宿主源码归因，不是通用 Repair 已完成的证据。

三次执行错误后生成阶段按原 self-check 上限停止，分类 probe_defect；没有把这些 error 当成有效的初始断言拒绝。

### 0002：先修正 Probe 解包错误，随后留下错误的大输入期望

首轮自检出现 `ValueError: not enough values to unpack (expected 4, got 3)`；模型修改 Probe 返回值处理后，后两轮转为正常断言失败。修复后的实现仅在 R3 大输入检查失败，观察值为 k0000/version=0/value-750。

生成数据采用 key=i%250，共 1000 行，因此同一 key 的出现位置是 k、k+250、k+500、k+750，最后一条为 k+750。最终 Probe 却使用 last_index=k+995 形成期望；例如 key=0 的正确最后记录在 750，而非 995。证据支持这个剩余问题仍来自 Probe 的 fixture 期望，不能据 reward/断言失败归咎 Solution。模型改写了参考合并 helper，但没有修正该索引，三次自检累计失败后分类 self_check_failure。

### 0003：初始/修复职责混淆与修复回归

首轮初始实现全部通过，但 Solution 在同版本取最后记录的行为上失败。模型随后把 Solution 改为保留最后同版本记录，第二轮初始及修复实现全部通过；这仍不满足修复任务必须存在初始失败的条件。

之后模型修改初始实现以引入缺陷，却又把 Solution 的同版本比较从 >= 改回 >。最终初始实现和修复实现均在 R2/R3 失败；修复实现不能通过，故第三轮仍失败。这里有持久源码修改与实际容器回归证据支持 Synthesis 的组件混淆和回归；没有充分证据指向基础设施故障。

候选 0002 和 0003 的同类失败只是暂停信号，**并不意味着已证实共同根因**：前者有 Probe 期望错误，后者有 Solution 语义错误。保留原生共同原因报告 `batch/diagnosis-0003.json`，不将类别相同当作语义证明。

## 阶段成本

| 候选 | 阶段 | 模型调用 | 工具调用 | 输入 Token | 输出 Token | 总 Token |
|---|---|---:|---:|---:|---:|---:|
| 0001 | 常规 Synthesis | 8 | 8 | 23,819 | 3,511 | 27,330 |
| 0001 | 失败自检后的调查/调整 | 6 | 6 | 66,369 | 4,763 | 71,132 |
| 0002 | 常规 Synthesis | 7 | 12 | 26,631 | 4,952 | 31,583 |
| 0002 | 失败自检后的调查/调整 | 4 | 4 | 62,858 | 5,033 | 67,891 |
| 0003 | 常规 Synthesis | 8 | 9 | 25,865 | 4,157 | 30,022 |
| 0003 | 失败自检后的调查/调整 | 12 | 12 | 139,464 | 3,177 | 142,641 |
| 合计 | | 45 | 51 | 345,006 | 25,593 | 370,599 |

常规 Synthesis 为 23 次调用/88,935 Token；失败自检后为 22 次调用/281,664 Token，占总 Token 约 76.0%。后者仍属于 Synthesis 自主调查和编辑，不是 Controller 授权的通用 Repair。API 观测耗时合计约 134.415 秒，自检工具观测耗时合计约 78.34 秒；这些是不同事件口径，不相加作为全程耗时，整次 wall time 为 222.165 秒。

每个候选调用 3 次 self_check，共 9 次；工具级状态保留 error 与 failed 的区别。尚无独立 Docker 测试 panel、Harbor trial 或冻结复验。宿主预检过程另外记录，不计入 51 次 Agent 工具调用。

API 调用、工具调用和输入/输出/总 Token 的账本对账差均为 0。阶段与候选分项、全部 API 尝试和工具活动位于 experiment-result.json 的 costs；未到达阶段保留 0 次观测，并在本报告标记 not_run。

## 单独分析只读与无进展调查

| 候选 | write_file | shell | self_check | list_files/read_file |
|---|---:|---:|---:|---:|
| 0001 | 7 | 2 | 3 | 2 |
| 0002 | 11 | 0 | 3 | 2 |
| 0003 | 10 | 6 | 3 | 2 |

只读调用和文件摘要未变化本身不代表无用：读取源码、构造对照或自检均可能必要。本轮没有候选由 no_progress 类别停止，也没有为节省调用跳过调查。

可确认的一处低效边界误解出现在候选 0003：一次 shell 在 /tmp 生成 vA/vB/vC 和输入；下一次 shell 又尝试运行它们，结果文件不存在。shell 每次使用新的可丢弃容器，前一调用的临时文件不会保留。该失败提供了应在同一次调查命令中完成临时 setup/check 的证据；并不能推导所有 shell 调查都应减少。原始命令与反馈保留在候选 trace 中，没有执行事后模型修复。

Probe 异常反馈目前仅包含 Requirement、类型和消息，缺少失败源码行的直接定位；这可能增加调查难度，尚不足量化其因果影响。候选 0001 的无依据注释修改、候选 0002 的 fixture 索引未修正，以及候选 0003 的正确 Solution 被回退，比单纯调用数量更能解释未完成的质量问题。

## 未到达阶段、比较边界与下一步

独立开发/验收 Test Agent、通用 Diagnosis、授权 Repair、Challenge、最终 Docker/Harbor、held-out 和三轮复验均为 **not_run**。没有单独测试的 import-safe 检查实际生成结果可评价；没有触发新诊断上下文管理，也不能声称历史 JSONDecodeError 已在完整流程修复。

与上一轮 40 次上限真正耗尽不同，这一轮在仍有 35 次模型调用余量时因原有重复质量失败暂停。提高预算给第三个候选提供了更多调查空间，但没有解决自检质量与组件归因问题。预算和提示同时变化，不能单独归因于其中之一；不同版本、条件下的运行不合并为成功率。

下一步优先把本次失效的 Probe 返回值一致性、fixture 期望及组件误修改作为开发回归证据，并评估给 Synthesis 更直接的自检异常定位信息或受控修复路径。不能只靠强制留出阶段调用解决尚未通过自检的问题；本轮没有后续阶段的实际成本数据，暂不实施动态预算或阶段预留。任何机制变化必须另行回归、冻结和使用新的 run ID。

## 工程交付与复现

- 代码/配置修改：`synthesis_agent/agent.py`、`independent_verification/agent.py`、`independent_verification/challenge.py` 的通用提示或 trace 元数据；`experiments/01_e2e_reliability/analysis.py`、`run.py` 的成本分项与动态报告；新增 `experiments/02_general_repair/e2e_exploration_protocol.json`，同步实验 README 和 `tests/test_e2e_reliability.py`。未新增 Orchestrator、Repair 实现或顶层目录。
- 正式运行前 `python3 -m unittest discover -s tests -v`：56 项，55 通过、1 项 opt-in 容器冒烟跳过；日志已保存为本次 `provenance/framework-tests.log`。脚本模型框架回归不算实时模型能力证据；本次 Self-check 另有真实 Docker 执行。
- `git diff --check` 通过。正式运行期间与运行后没有修改冻结源代码、输入或原始候选；报告、postrun-analysis.json 是新增的事后分析。未创建 Git commit。
- 保留用户原有 backup 未跟踪内容以及上轮未提交报告；没有覆盖历史运行。

```bash
python3 experiments/01_e2e_reliability/run.py \
  --protocol experiments/02_general_repair/e2e_exploration_protocol.json \
  --run-id NEW_UNIQUE_RUN_ID
```

原始本次结果为 experiment-result.json，暂停和各候选记录为 batch/batch.json，重复失败比较为 batch/diagnosis-0003.json，逐次自检与模型工具响应在各 candidate/trace.jsonl；postrun-analysis.json 保存事后汇总与完整性复核。
