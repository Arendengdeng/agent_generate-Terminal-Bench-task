# Synthesis Self-check：通用诊断、原子修复与回归实验

- experiment_id: `02_general_repair`
- run_ids: `selfcheck-replay-20261117-atomic-01`, `selfcheck-e2e-20261117-atomic-01`, `selfcheck-replay-20261117-atomic-02`, `selfcheck-e2e-20261117-atomic-02`
- 原始案例 run_id: `explore80-20261117T170350Z-77905313`
- Git 基线: `602ee8f`；工作分支: `feat/synthesis-self-check-repair`；未创建提交。
- 第一版 framework_code_version: `4f26a5893ae8b38e79f3fa4ac21d1c065d1ce6b34e57ab9cb85e699b30829182`
- 第二版 framework_code_version: `af29dd1b37b6c44c5918015dc5edea56207e6f2ed53744c5608189018b67cb09`

## 现有实现审查

原 runner 导入了 traceback，却只返回异常类型及最多 2000 字符消息；子进程输出是否可见取决于 Probe 自己的断言消息。原 evidence envelope 没有补充丢失的执行数据。模型对 tuple/dict 混用缺少直接失败行及局部值，但这只能说明证据缺口，不能证明补齐证据就能解决推理问题。

Synthesis 的调查仍在常规生成循环中，直接 `write_file` 可以覆盖任一可写组件。调用 self_check 前后的摘要有记录，但没有把归因、修改理由、文件范围、修复前后版本与回归决定绑定。self_check 原本已运行 Initial 和修复后的项目；缺失的是修改后强制执行以及已验证 Solution 的保护，不是缺少这两种执行。

三个案例的事后证据分别支持 Probe 数据结构错误、Probe fixture 期望错误，以及 Initial/Solution 职责混淆和 Solution 回退。错误类型、断言失败、reward 或相同停止类别均不能单独证明归因。历史 run 没有进入独立 RepairDispatcher，不应把本次改造描述成修复了该 Dispatcher 的既有失误。

## 最小实现及权限边界

生产修改只涉及 `synthesis_agent/agent.py`、`sandbox.py` 和新增的 `self_check.py`。保留既有 FileSet、DockerSandbox、trace、预算记账和 private envelope；没有建立第二套独立 Repair 或任务语义适配器。

- runner 记录失败 traceback、源码位置、基本类型局部值，以及 subprocess.run 命令、cwd、退出码、stdout/stderr、超时和参数引用的普通文件前后快照。只读取容器 `/app`、`/tmp`，不递归扫描；明确标记截断、深度限制和省略命令。大详情与小判定分离，宿主有界读取。
- 首次自检后只能经 `record_hypothesis`、`apply_repair` 修改。每文件必须声明路径、理由和内容，删除用 null；宿主核对父版本、证据引用、Requirement 和路径/预算，不以 JSONL/CSV 规则选择组件。
- 每个原子补丁自动复跑原有完整自检，自动调用也计入共享工具预算及原有失败次数。修改前、试修版、实际结果与回滚分别保留。未完全解决的试修标记 unresolved，不能 finish。
- 修复后全部通过时建立保护基线；后续退化整体回滚。Probe 改变时另用保护基线 Probe 检查修复后项目，防止弱化新 Probe 掩盖 Solution 退化。该保护不证明 Probe 充分性，独立测试与最终验收继续承担原职责。
- 新私有读取工具仅接受本轮白名单证据 ID；Independent Test 的公开读取接口仍拒绝 private 证据。外部 Repair 请求的 allowed_paths 与事务权限取交集。环境修改不扩展到宿主、镜像、安装器或网络。

## 冻结案例、实验与验证

`benchmarks/jsonl-latest-record/self_check_cases.json` 从原 build_log 按实际写入重建三个首次自检状态，补齐宿主添加的 Contract 附录与可信 Dockerfile，并逐项核对原 manifest/digest。0003 另保留第二轮修复后全通过的检查点。真实 Docker 重现了全部三个首次失败签名；真实 Docker 保护测试确认，恢复 0003 历史错误 Solution 后会检测失败并回滚到正确文件。

模型只收到 Plan、Contract、当前文件及运行观察。评估源码与人工审核反馈对照仅在模型停止后执行，不映射进模型容器、不反馈后续修复。没有使用 held-out 对照。评估同时要求 Initial 确实失败、Solution 通过 Contract 回归、最终 Probe 接受正确对照并以断言拒绝错误对照；error 不算拒绝。这是已知开发回归 panel，不能证明跨任务类型泛化或测试完备性。

每次重放独立使用 80 次模型、240 次工具、1,000,000 Token、8 次无持久修改调用和 3 次失败自检上限；每案新版重复三次、旧版一次。旧版从 Git HEAD 独立进程导入，仅添加恢复快照的输入上下文，不加入答案。第二轮为了减少恢复输入的不对称，旧版与新版均直接获得当前文件内容；旧版的补充数据在 system prompt 中明确标注为非指令数据。此实验适配及来源均记录于 protocol，不能把两轮结果合并为同一冻结比较。

第一轮旧版 0/3、新版 1/9 完成自主修复并通过评估。新版唯一成功为 0002 第三次：模型先修 Probe 解包，再识别并修正大输入期望，两次实际补丁均自动回归。其余八次在修改事务执行前触发无进展保护；宿主仍向模型展示已禁止的直接写入工具，以及恢复快照时重复读取文件的开销，是具体机制问题。第一轮三次旧版中有一次尚未执行首次自检即触发无进展保护，不能称为三个原始失败均被该旧版重放观察到。

第二版在自检后从模型可见工具列表移除直接写入操作，宿主拒绝检查继续保留；恢复快照时提供当前文件内容。没有改变预算、无进展阈值、自检失败上限、独立测试、Repair、Challenge 或最终验收规则。

第一轮完整 E2E 的候选通过 Synthesis 自检，但后续独立诊断耗尽共享 80 次模型调用，Controller 为 needs_review，独立验收 false；未获得 native accept，冻结复验未运行。实际消耗 136 次工具调用、400,211 报告 Token。Docker 无网络；Harbor 模式为 public，不宣称严格无网络验收。

第二版测试：`python3 -m unittest discover -s tests -v` 共 71 项，69 通过、2 项 opt-in 跳过；`SELF_CHECK_DOCKER=1 python3 -m unittest tests.test_synthesis_self_check -v` 共 15 项全部通过。默认套件内的脚本模型测试不是自主修复证据。测试日志保存在第二轮运行的 provenance；`git diff --check` 通过。

第二轮完整 E2E 生成了两个候选，均通过 Synthesis 自检。0001 进入最终验证的 Challenge，但以 `CHALLENGE_INCOMPLETE / repair_budget_exhausted` 返回 needs_review；0002 在独立测试修复阶段遇到共享模型预算耗尽。整批消耗 80 次模型调用、111 次工具调用、553,837 报告 Token，结束为 shared_budget_exhausted，原生 Controller 为 needs_review，独立验收 false。Harbor oracle/nop、held-out 及三轮冻结复验未运行；不能把进入 Challenge 等同于最终验收成功。运行期间源码完整性为 true。

第二轮 0001 的首次重放通过自主修复与外部回归。模型修复 `_expected` 的 tuple/dict 混用后，执行证据进一步暴露原 Solution 的同版本比较错误及 Initial 已经正确的问题；模型随后修改两者，又自主去除了试修 Initial 时误写的 NameError，保留已通过的 Solution。初始崩溃会被现有 Probe 的退出码断言视为初始失败；本次没有修改这一既有验收行为，模型最后自行将它改回可运行的逻辑缺陷。

0001 的另两次重放在三次失败自检上限停止。可核验的一次错误推理是认为 Python 稳定排序会保留同版本第一条；据此修改 fixture 仍不能使正确 Initial 失败，随后修好 Solution 时次数已耗尽。这与第一版工具仍暴露直接写入的问题不同：新接口已经执行了两个实际事务，剩余失败是模型对当前实现的错误归因及有限次数内未完成修复。没有放宽失败上限继续重试。

第二轮重放最终结果如下；12 次运行均观察到与冻结输入一致的原始失败签名，源码和输入完整性检查均通过。

| 原候选 | 旧版成功/运行 | 新版成功/运行 | 新版失败停止类别 |
|---|---:|---:|---|
| 0001 | 0/1 | 1/3 | 两次 self_check_failure |
| 0002 | 0/1 | 2/3 | 一次 self_check_failure |
| 0003 | 0/1 | 1/3 | 两次 no_progress |

新版共 **4/9** 次完成自主修改、Self-check 和外部回归，三个案例均至少成功一次。旧版只有每案一次，且输入恢复经过实验适配，不能由此估计稳定成功率或声称显著优势。新版总成本为 76 次模型调用、111 次工具调用、1,083,184 报告 Token；这是九次独立运行的合计，不是单次超过 1,000,000 Token 限额。旧版三次合计 24 次模型调用、27 次工具调用、322,649 Token。

0002 两次成功均保留原行为检查，先修 helper 解包，再修 1000 行 fixture 的最后记录期望，没有修改正确 Solution。一例错误提交了重复文件路径，宿主在文件修改前拒绝并保留记录，模型随后重新提交成功。另一失败运行误用 null 删除必需 Probe，随后虽恢复文件，仍未在三次失败内修完；宿主未允许 finish。

0003 成功运行在一个原子事务中分别修改 Initial 和 Solution：前者引入同版本选择错误，后者修正相同问题，Probe 不变；两侧真实执行及外部回归通过。其最初的 provisional hypothesis 猜测复制/环境故障并不正确，最终每文件修改理由才指向实际语义问题，不能把所有临时假设都标为正确归因。另外两次失败分别表现为错误反转比较规则后持续误判可丢弃容器状态，以及未提交补丁前耗尽无进展次数。

人工查看了四个成功运行的实际差异：没有以删除已有行为断言取得通过。但 0001 的 Probe 还额外加入了 import AST 检查；有限评估通过不能证明其符合所有“仅行为测试”的生成约束或具有充分性。本次没有出现自然运行中错误回退已验证 Solution、继而触发回滚的实例；这一保护的执行证据来自独立的框架测试与真实 Docker 历史故障注入，不能计为模型自主修复成功。

结论是通用机制已能实际执行有证据的多步修复、保存版本并强制回归，三个真实案例均有成功执行证据；**仍不能宣称模型能够稳定正确归因和修完，也未达到完整 E2E native accept**。剩余错误包括稳定排序理解、比较规则、修改内容与可丢弃环境状态的推理失误。本轮没有加入任务专用规则来替模型选择正确答案。

原始证据位于各 run 的 `comparison.json`、`replay-result.json`、`self-check-history.json`、`self-check/` 和 E2E `experiment-result.json`；第二轮另有 `postrun-analysis.json` 保存事后评审。所有失败版本与首次实验原始证据保留，没有覆盖或续跑直至成功。没有修改独立测试/Repair/Challenge 源码、Contract、原始报告、历史冻结输入或验收规则，也没有创建 accepted 导出。未创建 Git commit。

## 交付文件

- 生产：修改 `synthesis_agent/agent.py`、`synthesis_agent/sandbox.py`；新增 `synthesis_agent/self_check.py`。
- 框架测试：新增 `tests/test_synthesis_self_check.py`。
- 固定回归数据：新增 `benchmarks/jsonl-latest-record/self_check_cases.json`、`benchmarks/jsonl-latest-record/self_check_evaluation.py`。
- 实验：新增 `experiments/02_general_repair/self_check_replay.py`、`experiments/02_general_repair/self_check_e2e_protocol.json`；更新同目录 `README.md`。
- 文档：更新根 `README.md`、追加 `reports/02_general_repair/runs.md`，新增本报告。共 12 个文件，已显式暂存；用户原有 backup 未跟踪内容未改动。四个运行的冻结输入在交付前重新逐项核对哈希一致。
