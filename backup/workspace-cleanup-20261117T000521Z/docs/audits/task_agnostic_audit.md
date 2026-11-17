# Task-Agnostic Architecture Audit

审计日期：2026-11-16。对象：当前工作区实际源码（HEAD `c8be56d` 加现有未提交修改），不是 `runs/` 或评估库里的历史源码快照。

本次仅新增本文档；未修改源码、测试或既有证据，未读取密钥配置，未调用真实模型，未启动 Docker/Harbor、完整 Pipeline 或历史执行重放。运行了 29 项定向离线单元测试及少量纯函数检查。测试中的 ScriptedClient、Mock、CollectionStub 不是真实模型或容器。

## 1. 总体判断

**结论：部分通用。它是具有多任务能力的 Python 标准库 CLI 数据处理修复框架，尚不是可仅凭任意 Plan/Contract 自动完成验收的任务无关框架，也不能概括为主要只能处理 CSV。**

支持多任务的实证：输入校验、Requirement 映射、隔离执行、产物传输、评分状态和 Controller 不需要 CSV 字段；既有实现库覆盖 JSONL 聚合及目录摘要，两个变体各有实际评分记录。限制也很明确：Python、`/app`、标准库、固定候选布局、pytest、独立容器和文本文件工具是共同协议。

最重要的审计结果：

1. **P1 / C：CSV 语义检查进入了必经通用门禁，且启用方式及输入/输出归属存在已复现的误拦。** 不是所有任务都执行邮箱规则，但所有候选都经过包含这些规则的检查器。
2. **P1 / C：一般 Test Repair 没有通用归因/补丁证明接口。** 目前仅支持固定整数 stdout 和一个固定路径、固定措辞的 JSON doubling 任务。已有六种 Contract 全部在这些证明规则之外；有测试缺陷时不能据此自动修复。
3. **P1 / C：定向诊断证据包对一般漏检场景可能没有源码。** JSON 特例能补充位置，一般任务只有违规实现通过时不能获得同等信息，且诊断不允许补读文件。
4. Challenge 增补测试有另一条基于见证、独立模型审查和对照复验的通路；**不能把一般 Test Repair 的限制错误推广成 Challenge 一律不能修复非 CSV 任务**。
5. **只有 Plan/Contract 不足以获得完整 `accept`。** Controller 还要求绑定 Contract 的已审查 feedback/holdout 正确与违规实现。当前没有从任意 Contract 自动生成并确认这四类独立证据的通用能力。

未发现本次范围内足以确认的 P0。P1 表示阻断自动化或错误阻断受支持任务；P2 表示明确的支持边界、局部能力缺口或证据不足。A/B 项标 P2 表示边界维护优先级，并非认定它是缺陷。D 项仅报告待验证事项，不当作已确认故障。

分类：A = 真正通用的框架逻辑；B = 合理的专用适配器或明确限定的规则；C = 不应放在通用层的任务特定假设；D = 尚缺通用性证据。

## 2. 实际调用路径及模块评估

```text
Plan / Contract
  → SynthesisAgent._run → validate_inputs → 生成候选 / self_check
  → CandidateTask.load → prepare_panel → check_candidate
       └─ check_instruction：附录一致性 + 有条件启用的 CSV 规则
  → TestAgent.generate → validate_test_input → collect / Requirement Mapping
  → repair_tests（普通 all 默认启用）
       ├─ 执行通过：直接进入后续阶段
       └─ 失败：对照门槛 → prepare_feedback → evidence_packet → analyze
                    → verify_test_diagnosis → repair → verify_test_patch → 全量复验
  → Challenge（普通 all 默认启用）
       → validate_witness → review_witness → 见证执行 / 两次评分 / audit_trial
       → decide_challenge → 增补新测试文件 → review_patch → 回归
  → export_task → Harbor lint → 冻结 → Docker / Harbor 对照评分
  → panel.summarize → controller.decide

显式 --repair：进入 RepairDispatcher；不与 Challenge 同时运行。
独立 run_e2e：已有 candidate / tests / 两份面板清单 → 健壮性准备
             → 发现漏洞 → 增补修复 → 三轮终端评分；不是 Plan 起点的生成入口。
```

路径证据：`synthesis_agent/agent.py:96`、`independent_verification/pipeline.py:55`、`:107`、`:141`、`:159`、`:196`、`:276`；互斥条件在 `pipeline.py:64`；E2E 输入在 `scripts/challenge_agent/run_e2e.py:35`、`:58`。

| 模块 | 分类 | 能否原样用于非 CSV | 实际边界 / 风险 | 详细发现 |
|---|---|---|---|---|
| Task Plan / Contract 输入 | B | 能，限受支持方向 | Python stdlib CLI、`/app`、正整数 limits | F04 |
| Synthesis Agent | A/B/D | 接口能；生成质量待证 | 固定候选文件协议，真实跨任务生成未由实现库证明 | F04、F05、F13 |
| Contract–Instruction 检查 | A+C+D | 非 CSV 多数仅检查附录 | CSV 子串误启用；未做一般语义一致性验证 | F01 |
| Test Agent | A/B | 能 | pytest、固定测试路径；不继承初始数据及依赖 | F05 |
| Test Diagnosis | A+C | 普通失败可；一般漏检信息不足 | 源码选取依赖 traceback 或 JSON 特例位置 | F03 |
| Test Repair 授权 / 补丁检查 | C | 只有两个极窄证明形态 | 六个现有 Contract 均不支持一般测试修复 | F02 |
| Challenge Agent / 见证执行 | A/B/D | 能，限见证 DSL 表达范围 | 文本、等值比较、三个文件解析器 | F06、F13 |
| Independent Reviewer | A/D | 提示及上下文可复用 | 隔离对话，不是独立模型或形式证明 | F07 |
| Controller | A | 能 | 审查证据、对照状态、完整性，不检查 email/CSV | F08 |
| Repair Dispatcher | A + 继承 C | 静态修复可；测试修复受限 | scope 路由通用，运行失败归因不通用 | F02、F08 |
| 静态检查 | A/B + 继承 C | 能，符合候选协议时 | 固定可信 Dockerfile；CSV 门禁可能误拦 | F01、F04 |
| Docker / Harbor / exporter | A/B/D | 能 | 独立 verifier、pytest、固定资源及超时协议 | F09、F12 |
| 六规格 / 实现评估库 | B | 支持 JSONL / manifest 现有适配器 | 固定六份 Contract 摘要、固定题型与评分夹具 | F10 |
| 通用 E2E 验收入口 | A/B/D | 可接收非 CSV 候选 | 额外输入、发现漏洞要求；passed 不等于 Controller accept | F11 |
| CSV 历史验收脚本 | B | 不应直接用于其他任务 | 路径、字段和面板数量是显式适配器 | F10 |

## 3. 发现与代码证据

### F01 — CSV 专用一致性规则处于通用阻断路径，存在误拦

**分类 C；P1；已确认。** 其中附录相等检查是 A，未覆盖的语义是 D。

- 文件/函数：`synthesis_agent/consistency.py:17` `check_instruction`；`:34` 为 `csv = 'csv' in (inputs + output).lower()`；`:38` 仅从 `output_spec + requirements` 提取受支持行尾；`:48` 对 instruction 中所有匹配行尾的分句执行阻断；`:50` 是固定 email 空值规则。
- 调用与触发：`candidate.py:83` 静态检查、`agent.py:103` Test 输入、`diagnosis.py:9`、`attribution.py:88`/`:128` 都调用该检查。`pipeline.py:114` 静态失败会在 preflight 和 Test 模型调用前返回；`controller.py:95` 归给 synthesis。不是仅供 CSV 调试选择的可选检查。
- 任务假设：出现 `csv` 即代表应启用 CSV 规则；instruction 中谈到的 LF/CRLF 都归属输出；邮箱字段叫 `email` 并使用受识别的固定表述。
- 本次纯函数复现 1：复制 `jsonl-original`，仅在 input_spec 增加 `输入为 JSONL，不是 CSV；输入行尾使用 LF。`，instruction 原样复述此条。结果 `blocked / UNSUPPORTED_CSV_LINE_ENDING`，指向 JSON 的 output_spec。这里规则是 Contract 已授权的**输入**限制，也不是 CSV 任务。
- 复现 2：CSV input_spec 增加 `输入行尾使用 CRLF。`，instruction 原样复述，也被相同规则阻断；因为提取授权规则时不读 input_spec。
- 影响：合法非 CSV Contract 可以被 CSV 专用规则误拦；真实 CSV 也存在输入/输出混淆。默认四个非 CSV 示例不含该子串，未触发邮箱/行尾规则，不能声称它们全部已被破坏。
- 最小建议：把附录比较留在通用层；语义规则通过显式任务/格式能力启用，区分输入与输出归属；无法确定归属时报告不支持，不以 CSV 子串猜测后硬阻断。为上述两个例子补回归。
- 覆盖缺口：非 CSV 返回 `no_findings` 主要表示这些专用规则未启用；也不检查分组键、字段集合、排序等一般矛盾。附录 marker 缺失不会单独报错。当前返回值及 `README.md:72` 已明确有限性，故不认定为“实现了通用语义证明”的虚假宣称。

### F02 — 一般 Test Repair 的通用入口实际只有两类样例证明

**分类 C；P1；已确认。** 保守拒绝无证明补丁本身是 A；把证明形态固定在核心中是泛化障碍。

- 文件/函数：`independent_verification/attribution.py:20` `_assertion`；`:25` 精确匹配 `Print (-?\d+) and exit successfully.`，`:26` 匹配 `(-?\d+) followed by newline.`，`:28` 要求 `No input.`，`:48` 要求直接 stdout 字面量等式。`:90` 和 `:130` 硬接 JSON 特例分支。
- `json_attribution.py:11`–`:18` 的 `supported` 精确要求输入为 `Integer n in [0,10].`、固定 JSON output_spec 和命令 `python /app/clean.py <n>`；`:23` 要求完整固定 Requirement 文本；`:54` 连测试调用也固定为 `python3 /app/clean.py`；`:56` 固定字段 `value/double` 与 `2*n`；`:66` 固定弱断言 AST。
- 触发：只有执行失败并进入一般测试修复时才调用证明器。`test_repair_workflow.py:49` 执行已通过就继续；失败则 `:74` 验证诊断、`:98` 验证补丁；不支持在 `:105` 转 `needs_review`。Dispatcher 对应 `repair.py:204`–`:215`、`:287`，同样受限。
- 本次检查：六份 Contract 均 `json_attribution.supported == False`；用各 Contract 完整 R1 引文进入 `_assertion`，全部得到 `Contract is outside supported literal-stdout proof rules`。证明条件读取整个 input/output_spec，所以不是更换 requirement_id 就能解决。
- 影响：JSONL、目录摘要乃至六份库内 CSV Contract 的一般测试缺陷都无法使用这条通路自动修复。固定 JSON 特例路径仅改名为 `/app/double.py` 也不再受支持；`clean.py` 字样在这里属于 JSON 演示任务过拟合，不是 CSV 语义。
- 最小建议：先显式输出支持能力和 `unsupported_proof_rule`，避免先付费诊断再失败；把现有两个证明器注册为独立可选适配器，通过配置选择，保留无证明即停的门槛。新领域的自动修复需要新增经验证的证明适配器，不能只换自然语言 Contract。
- 不适用范围：`challenge_workflow.py:183`–`:228` 是另一条 Controller 授权的增补测试路线，通过见证和独立补丁审查，不调用这两个 AST 修补证明器。

### F03 — 定向证据包偏向“合法实现失败”，一般漏检时可能丢失必要源码

**分类 C；P1；已确认信息缺口，未声称真实模型必然失败。**

- 文件/函数：`independent_verification/diagnosis.py:18` `evidence_packet`；`:25`–`:32` 优先 known 的 call failure，其次 oracle failure，最后 `:outcome`；`:46`、`:56` 只有 host 位置或 traceback 才调用 `add_source`。`:5`、`:12` 的主动位置发现只来自 JSON 特例 `supported_diagnoses`。
- 通路：两种一般修复入口均使用 `prepare_feedback`；`independent_verification/agent.py:168` 诊断只给 `diagnose/classify_failure/needs_review`，`:342` 以 packet 作为完整用户输入，没有 read_file 或分页反馈能力。
- 任务假设：测试缺陷能够由失败断言位置找到，或者属于固定 JSON AST 形态。**缺失断言通常产生违规实现通过，不产生失败 traceback。**
- 本次纯函数复现：JSONL Contract、已有 `test_behavior.py`、仅 `invalid-000:outcome` 的反馈，得到 `source_excerpts=[]`、`host_supported_diagnoses=[]`，即使调用者提供了测试源码字典也是如此。这是包构建逻辑的确定性输出。
- 影响：普通漏检没有足够源代码让模型引用有效行号；辅助函数、跨文件 fixture 或超过局部 ±8 行的上下文也可能不足。结果应未决，不是放宽验证；与 F02 叠加，但即使以后增加证明器，该信息缺口仍存在。
- 最小建议：基于 Requirement Mapping 把对应测试函数及引用 fixture 的有界源码纳入包；对通过的违规对照附上可公开的 Contract 见证。不存在定位时明确返回证据不足，或提供受总预算限制的源码补充读取能力。无需恢复完整原始日志。
- 通用部分 A：拒绝 holdout、保留输入/测试摘要、精确源码行号、删掉私有日志都不依赖 CSV，应保留。

### F04 — 输入及候选协议有明确支持范围，并非 CSV 隐含限定

**分类 B；P2；已确认边界。**

- 文件/函数：`synthesis_agent/inputs.py:14` `validate_inputs`，`:16` 仅 cli_repair/code_repair，`:21` 仅 Python/Linux Docker/cli_data_processing，`:25` 工作区 `/app` 且命令以 python/python3 开始，`:28` python-stdlib，`:37` 产物必须在 `/app/` 下。`agent.py:98`、`candidate.py:61`、Test 的 `agent.py:99` 共同执行这些限制。
- 固定结构：`candidate.py:33` 强制 `draft/instruction.md`、`draft/environment`、`draft/solution/solve.sh`；`:97` 和 `:112` 要求 environment 为 Dockerfile + app/、可信固定 Dockerfile。`synthesis_agent/agent.py:158`、`:181` 实施生成路径约束。
- 假设及影响：单 Linux 容器、Python CLI 修复、文件交付和 shell 安装器；JavaScript、pip、服务状态、任意 workspace、任意 Dockerfile 会在输入或静态阶段失败，单换 Plan 不足。此边界不是 CSV 规则，当前 `README.md:5` 与 `pyproject.toml:9` 的描述也明确是 Python CLI 修复，未发现主入口宣称支持所有语言的证据。
- 最小建议：统一暴露 capability/profile 描述，把所有入口的错误与文档关联到该 profile；保持明确拒绝。只有确实要支持其他方向时才增运行 profile，不必为此次审计重构。

### F05 — 文本文件工具、pytest 及 fixture 白名单限制了任务形态

**分类 B；P2；已确认边界。**

- 文件/函数：`synthesis_agent/files.py:72` `FileSet.put` 只接受字符串并 UTF-8 编码；`candidate.py:52` 解码候选文件；`independent_verification/common.py:54` `test_path` 只接顶层 `test_*.py` 与 `fixtures/*.{txt,json,csv,jsonl}`。
- `independent_verification/agent.py:31` PROMPT 指定 pytest，`:45` 提示 verifier 只收 deliverables，`:47` 不允许 conftest、插件、安装器。`exporter.py:39` 对导入的冻结测试再次执行白名单，并非只有 prompt 提示。
- 假设及影响：生成产物、初始材料和静态 fixture 都是 UTF-8 文本，测试机制是 pytest。二进制输入可由测试中的 Python 代码在 `/tmp` 运行时创建，目录摘要库正采用此方式；不能把它误判为“不支持读取二进制数据”。但不能直接通过文件工具提交原始二进制 seed/fixture；`.yaml`、`.bin` fixture 或测试辅助包不能原样使用。
- 最小建议：文档区分“文本生成包”与“被测程序可以处理的二进制数据”；按需增加受控二进制数据编码或 fixture 类型声明，不默认扩大执行权限。

### F06 — Challenge 观察 DSL 多格式通用，但不是任意 Contract 见证语言

**分类 B + D；P2；表达边界已确认，更多领域可用性待验证。**

- 文件/函数：`independent_verification/challenge.py:118` `validate_witness`，`:129` 要求 argv 的 Python 和脚本与 Contract 对应，`:134` fixtures 走 FileSet，`:146`–`:161` 只接受既定观察类型。`:210` `PARSED_FILE_BRANCH` 仅支持 json/jsonl/csv，`:223` 根据断言选择解析模板。
- 不是 CSV 固定语义：CSV parser 仅由 `source=parsed_file,path=[...,"csv"]` 显式选择；无 email/字段约束。JSON、JSONL 选择相应 parser。观察器执行期的 `csv` import 不等于所有任务都按 CSV 验证。
- 表达假设：文本 fixture、单次 Python CLI、等值比较和固定解析器。`:179` subprocess 使用 `text=True`，`:194` file/unchanged 使用 `read_text()`，会发生换行归一化；所谓 raw text 比较不等于逐字节比较。字节精确 CRLF、二进制一致性、权限、符号链接等不能由现有这些观察操作符完整表达。
- 影响：不支持的行为可能无法确认 Challenge，正确对照门槛通常会使不合适见证停在未确认；本次没有据此认定会误授权。Test Agent 仍可编写 Python 行为测试，两种能力不可混同。
- 最小建议：把观察能力列入机器可读支持声明；仅在需要时增加 bytes/base64、文件元数据等独立操作符及对应 Reviewer 说明；不强行让 JSON parser 验证其他格式。

### F07 — Reviewer 的信息隔离成立，认识上的独立性尚未证实

**分类 A + D；P2。**

- 文件/函数：`challenge.py:374` `review_witness` 重新构造 messages，仅发送 Contract 和去掉 rationale 的 witness；`:104` REVIEW_PROMPT 要求合法输入、每个断言均可由 Contract 推导。`challenge_workflow.py:248` `review_patch` 仅接 Contract/before/after，不发送候选实现、参考输出或 reward。健壮性 Reviewer 在 `robustness.py:237` 采用独立上下文。
- 主验证：`challenge_workflow.py:59` 先审查，再在 `:65`–`:80` 要求见证拒绝候选、接受 Oracle 和合法替代实现。并非拿 Oracle 输出作为预期值。
- 假设及影响：独立意味着消息隔离，不意味着不同供应商、模型、训练来源或形式证明；`challenge.py:26` Calls 复用传入 client/config，`challenge_workflow.py:149` 修复审查仍可使用同一 client。模型可能存在相关误解，但这尚是 D，未证实跨任务误判。
- 最小建议：保留隔离，把报告中的独立性精确表述为上下文独立；按需允许 Reviewer 单独配置模型并用非 CSV 盲测评估。不应以增加一次同模型审查就宣称一般语义证明。

### F08 — Controller 状态与修复路由不依赖 CSV

**分类 A；P2（维护项，无已确认任务耦合缺陷）。**

- 文件/函数：`independent_verification/controller.py:18` `decide`；`:50` Challenge 完整性，`:62` Repair workflow 完整性，`:95` 静态失败归 synthesis，`:163`–`:172` 根据各类对照异常报告调查而非仅凭 Oracle 归因，`:174`–`:194` 检查完整独立面板与后端一致性，`:224` 最终 `accept`。
- Challenge 专用归因 `controller.py:357` `decide_challenge` 根据 Contract/witness 摘要、见证对照、两次可复现通过评分和审计结果授权 tests repair；没有 CSV、邮箱或 LF 判断。
- Repair Dispatcher 的 `repair.py:23` SCOPES、`:265` RepairRequest、`:298` 不可变 Contract、`:303` 路径 scope 都是框架约束。`:153` 拒绝外部未验证归因，运行失败并不会随模型自报自动归为 solution/environment；F02 的特定证明器才是测试修复瓶颈。
- 假设及影响：任务必须能提供有限的独立正确/违规对照和二元评分，不证明所有输入正确。`panel.py:147` 要求 feedback/holdout 各有 correct/invalid；传一份 `--known-correct` 不会自动成为已确认独立证据，`panel.py:69`–`:105` 还要求摘要、审查和证据。
- 最小建议：保留状态与证据门槛；把缺少面板与不支持证明器分别显示，避免用户误认是 CSV 验收失败。没有理由为非 CSV 增加 Controller 特判。

实际状态对照如下，不存在统一的 `Accepted / Rejected / Unresolved` 三值枚举：

| 用户概念 | 源码中的实际状态 | 条件 |
|---|---|---|
| Accepted | Controller `accept` | 完整阶段、基本对照正确、审查面板充分、后端一致、无未决问题 |
| Rejected（违规实现正常拒绝） | completed + reward=0；`panel.outcome=fail` | 正常行为断言失败，非异常、超时或收集错误 |
| Rejected（无效 Challenge） | sample `rejected` | 已确认违规，但冻结套件已经拒绝它，`challenge_workflow.py:92` |
| Unresolved | `needs_review`、campaign `unresolved`、workflow `unresolved_issues` | 归因不支持、证据不足、预算耗尽、回归未解决 |
| 执行错误 | `error/cancelled` | 不算正常拒绝；Controller 不接受 |
| 仅检查/导出 | `not_evaluated` | 部分阶段，不是 Accepted |

### F09 — 执行器和 LF shell 检查是运行协议，不是 CSV 验收硬编码

**分类 A/B；P2（维护项）。**

- 文件/函数：`docker_test_runner.py:103` `_trial`，`:129` 从 Contract artifact_paths 导出真实产物，`:141` 销毁解法容器，再导入 verifier；`:150` 冻结测试及 artifact_policy。`exporter.py:17` 从 Contract 构造产物策略，`:54` 构造 Harbor artifacts。`harbor.py:125` 校验固定 Harbor 版本，`:141` 验证 TOML/lint。
- 评分：`wrapper.py:54` `classify` 校验 nodeids、setup/call/teardown、AssertionError 和退出码。测试配置、skip/xfail、异常状态控制是 pytest 协议，不读 CSV 内容。
- `synthesis_agent/agent.py:192` 检查 `solve.sh` LF，`candidate.py:93` 检查 solution 的 `.sh` 不含 CR。这是 Linux shell 可执行性要求，**不是强制 CSV/JSON 产物 LF**；未见 Docker/Harbor 全局替换数据文件 CRLF 的逻辑。
- 假设及影响：被测功能能通过独立容器中的交付文件复现；初始非交付样本、服务状态、网络依赖不能隐式继承。对现有 JSONL/manifest 同样适用。
- 最小建议：保留隔离和文件摘要；文档明确 shell 源码行尾与任务输出行尾的对象区别，不删除合理运行约束。

### F10 — 六规格和实现库是显式有限适配器；专用字符串大多合理隔离

**分类 B；P2；已确认。**

- 文件/函数：`synthesis_agent/candidate_batch/specs.py:9` `default_specs` 枚举三 family × 两 variant；`:58` `validate_specs` 明确拒绝其他 control recipe。`candidate_batch/controls.py:17` 的 CSV email/name、`:67` JSONL、`:163` ARTIFACT 路径映射仅用于相应对照构造，不是主 Agent 的默认任务规则。
- `implementation_library/library.py:25` SUPPORTED_CONTRACTS 固定六个摘要，`:139`–`:151` 验证六任务配额和产物；`recipes.py`、`witnesses.py:20` 的 expected 按 family 分派，是针对冻结 Contract 的有限语义评估器。新 Contract 不能复用旧摘要与标签。
- 容易误报的例子：`implementation_library/scoring.py:88` 的 CSV 禁止 `\r` 只在 `KIND=='overstrict'` 下触发；`:92` 默认 `kind='complete'`。这是刻意构造的过严评分对照，不是通用验收要求。`witnesses.py:158` 按解析结果比较，`tests/test_implementation_library.py:18` 实际测试 LF/CRLF 等价。
- 历史适配器：`scripts/challenge_agent/csv_e2e.py:26` `prepare` 强制 9 valid / 24 invalid（`:30`）并安装 `/app/clean.py`（`:41`）；它调用通用 `run_acceptance`（`:88`），通用入口没有反向导入该适配器。另两个 `scripts/*acceptance.py` 的 clean.py 数字/JSON 样例也不能仅凭路径名判定为 CSV。
- 影响：新增任务可以绕过内置 recipe，向通用 verify 传新的 candidate/controls 清单；但若要求自动生成同等级实现库、标签和独立语义见证，就必须增加题型适配器及冻结证据。现有库不是任意自然语言 Contract 解释器。
- 最小建议：保持冻结语义与主框架隔离，显式标记 family recipe 能力；新增领域时增加适配器和数据，不篡改旧 Contract 标签。

### F11 — “通用 E2E 验收通过”不等于一般 Controller Accepted

**分类 B + D；P2；两种通过语义的差异已确认。**

- 文件/函数：`scripts/challenge_agent/run_e2e.py:58` 要求已有 candidate/tests/controls_manifest/panel_manifest；不接 Plan。`acceptance.py:100` 只允许已确认 feedback-correct controls，历史面板另行读取（`:110`），不能直接把完整四类 controls_manifest 原样传入此接口。
- `acceptance.py:300` 未找到 confirmed gap 返回 `not_demonstrated`；`:309` 要求至少修复一次。对于已经充分的测试，不发现漏洞不是通用任务失败，而是没有展示“发现后修复”的实验过程。
- `acceptance.py:323` 终端调用 verify 记录 Controller 决定；`:338` 把它保留，但 `:342` 根据独立 matrix 判定，`:347` 置 `status='passed'`，没有要求 `final.controller_decision.decision == 'accept'`。传给终端的历史标签没有自动变成 Contract 审查标签，面板要求不同可令 Controller 未决。
- 假设及影响：这是 Challenge/Repair 展示加历史回归的验收协议，而非任意任务最终 Accepted 的同义入口。该区别不是 CSV 特定，但会使跨任务证据被高估。文档 `docs/guides/challenge-e2e.md:35` 描述了实验步骤，不能据“通用入口”推导任意任务都能通过。
- 最小建议：输出显式区分 `challenge_repair_demonstrated`、历史回归结果和 `controller_accept`；若目标是正式 Accepted，使用完整已审查四类面板及 Controller 门禁；无需降低实验原有通过标准。

### F12 — 固定资源/套件超时未完全随 Contract 变化

**分类 D；P2；固定值已确认，实际误伤尚未验证。**

- 文件/函数：`synthesis_agent/inputs.py:54` 接收额外正整数 limits；生成阶段 `synthesis_agent/agent.py:102` 检查 command_timeout_sec 不超过配置。`DockerTestRunner.__init__` 在 `docker_test_runner.py:48` 默认整套 120 秒；解法执行在 `:125` 固定 300 秒；`exporter.py:62`–`:66` 固定 agent=300、verifier=120、CPU=1、memory=512 MB。
- 假设及影响：任务较小、整套测试在默认预算内。`max_input_lines` 等业务 limits 要由生成的测试或专用适配器解释，不会自动成为全部执行器的强制约束。单条命令合法不保证大量测试仍在整套 120 秒内。
- 最小建议：先明确 Contract limits 哪些只是业务域、哪些是运行资源；支持的运行资源从同一配置导出，超范围预检明确拒绝。后续用非 CSV 边界任务测量，当前不认定已有合法任务必然超时。

### F13 — Prompt 未发现 CSV 默认任务模板，但有一个历史路径示例

**分类 A + D；P2。**

- 文件/片段：`synthesis_agent/agent.py:37` SYSTEM_PROMPT 明确根据实际 Plan/Contract、不得替换 stock task；`independent_verification/agent.py:31` PROMPT 按 Contract 测试、`:39` 禁止 instruction 额外加约束。没有预置 email/name、CSV 去重或保留第一行等范例。
- `challenge.py:97` 给出 `["python3", "/app/clean.py", "7"]` 示例，属于路径锚点；实际 validator 在 `:130` 用 `command[1]`，不会强制所有任务叫 clean.py。无法仅凭该示例确认模型会默认生成 CSV；`clean.py` 也用于 JSON 演示。
- 假设及影响：模型能正确把文字例子迁移到 Contract 命令；未调用真实模型验证。固定 Python/pytest 提示是 F04/F05 已声明能力，不是隐藏 CSV 假设。
- 最小建议：可将此示例替换为从当前 Contract 派生的 argv，消除不必要路径锚点；不要在没有生成样本证据时把提示偏置当成已确认缺陷。

## 4. 跨任务兼容性矩阵

### 4.1 六种现有 Contract

规格来自 `synthesis_agent/candidate_batch/specs.py:9`，并非六个互不相关的任务领域。全部满足相同 Python CLI 运行协议。

| Contract | 语义及交付路径 | 本次输入校验 / 同文 instruction 有限检查 | 主生成/测试/执行代码需按题修改吗 | 一般 Test Repair 主机证明 | 既有完整夹具评分摘要 |
|---|---|---|---|---|---|
| csv-original | 邮箱归一化，首次姓名；`/app/clean.py` | 通过 / no_findings | 不需；CSV 规则会启用 | 不支持 | Docker/Harbor 各接受 5 正确、拒绝 9 违规 |
| csv-variant | 保留最后姓名，仍按首次出现排序；同路径 | 通过 / no_findings | 不需；CSV 规则会启用 | 不支持 | 同上 |
| jsonl-original | service+level 分组 count/sum；`/app/summarize.py` | 通过 / no_findings | 不需；没有 CSV 行尾/邮箱语义检查 | 不支持 | 同上 |
| jsonl-variant | 仅 service 分组，增加 max；同路径 | 通过 / no_findings | 不需；同上 | 不支持 | 同上 |
| manifest-original | 每文件 path/size/hash；`/app/src/manifest.py` | 通过 / no_findings | 不需；支持目录产物范围 | 不支持 | 同上 |
| manifest-variant | 按摘要分组 paths/size/hash；同路径 | 通过 / no_findings | 不需；同上 | 不支持 | 同上 |

“同文 instruction”是本次以 objective/input_spec/output_spec 拼接的纯函数输入，不代表模型生成的 instruction 通过，也不代表一般语义一致。

历史结果来源：`evaluation_library/RESULTS.json:1460`、`:1594`、`:1728`、`:1862`、`:1996`、`:2130` 的 `complete--*`；每个任务 feedback=3 正确+5 违规，holdout=2 正确+4 违规，无后端差异；库共 30 正确、54 违规。本次核对了 JSON 内容和代码适配路径，**未解压并重放归档原始 Docker/Harbor 证据**；`RESULTS.json:25` 明确原始重放需恢复归档。以上为既有证据摘要，不是本轮新增执行结果。

证明强度：`scoring.py:104`、`:107`、`:114` 明确夹具为 hand-authored，不是模型生成；`RESULTS.json:38` 明确不证明 Planner→Controller 自主闭环。库中的 source review/expected/witnesses 是专用适配器提供的有限语义，不代表通用模型自行完成审查。

### 4.2 新任务替换后，各能力会发生什么

| 能力 | 全新 JSON CLI | 全新文件系统 CLI | 超出当前 profile（其他语言、依赖、服务） |
|---|---|---|---|
| Plan/Contract 校验 | 满足字段和 stdlib 方向则通过 | 同左 | 输入阶段拒绝 |
| Synthesis / 独立 Test 生成 | 可原样调用，质量需实测 | 可原样调用；运行时创建二进制输入 | 需新增 profile/执行支持 |
| 一致性检查 | 附录检查可用；一般 JSON 语义未验证 | 附录检查可用；一般文件语义未验证 | 到此之前通常已被拒绝 |
| Docker/Harbor 评分、导出、Controller | 原样工作，需合法包、独立面板和测试 | 同左；只传声明的文件产物 | 固定运行协议不能直接满足 |
| 一般失败后的 Test Repair | 不是固定 doubling/stdout 形态则未决 | 未决 | 不支持 |
| Challenge 发现及新增测试 | 文本/JSON 等值见证可表达时可进入 | 目录摘要文本/JSON 可；元数据/二进制见证受限 | Python argv、环境及 DSL 不支持 |
| 内置对照及实现库自动构造 | 新语义需新增适配器 | 新语义需新增适配器 | 还需新增运行支持 |
| 仅换 Plan/Contract 即完整 accept | 不足：还缺已审查独立面板，可能遇修复能力缺口 | 同左 | 不能，首先卡输入/环境 |

具体回答：

1. **原样工作的模块**：共同 profile 内的输入解析、生成工具协议、pytest 测试生成与收集、Requirement 映射、交付文件隔离和哈希、导出、Docker/Harbor 驱动、对照统计、Controller、Dispatcher 版本与 scope 管理。
2. **会失败或未验证的模块**：越界 Plan 在 validate_inputs 失败；新题的一般 Test Repair 在主机证明器停；非 CSV 一般 instruction 语义未被静态证明；漏检诊断可能没有源码；某些 Challenge 无可表达见证；无面板不能 accept。它们并不都表现为程序异常，更多是显式拒绝或 needs_review。
3. **依赖适配器的能力**：独立标签、可信对照构造、有限语义 expected/witness、自动测试补丁证明、复杂观察器。通用测试生成本身没有 family 枚举限制。
4. **新增任务需要改什么**：仅想尝试生成并执行一个符合 profile 的新题，不需要改核心；要完整 accept，需要新增任务专用面板和审查数据；要自动构造这些证据或修复一般测试缺陷，现状需新增 Python 适配器，并且 F02 的硬接分支还需要改核心分派。现有配置没有通用注册接口。
5. **CSV 规则会否错误阻断非 CSV**：会，F01 已纯函数复现；四个默认非 CSV Contract 目前没有触发此误拦。CSV shell LF 检查、可选 CSV parser、评估库 overstrict 夹具不应与该误拦混为一谈。

## 5. 最近修改的专项结论

对比当前 `git diff` 与 HEAD，并检查新增未跟踪文件 `consistency.py`、`diagnosis.py`；没有把改动归因给未检查的历史提交。

| 修改点 | 真正基于 Contract 的部分 | 仍依赖固定样例的部分 | 对非 CSV 的结论 |
|---|---|---|---|
| Contract–Instruction 一致性 | 附录结构相等、Contract 摘要、不可变输入 | CSV 子串、行尾正则、email 空值正则 | 有限检查会跳过；F01 有确定误拦 |
| Test Diagnosis 定向包 | Requirement Mapping、反馈/源码版本、拒绝 holdout、精确失败位置 | 主动支持位置仅为固定 JSON；一般通过样本不提供源码 | F03 是新增压缩机制的兼容性缺口 |
| Test Repair 授权 | 完整 Requirement 引文、对照真实失败、父版本摘要、不可越权 | literal stdout 与 finite JSON AST 证明 | 加了 drift 门禁，没有因此获得一般修复能力；F02 是既有窄规则，不能误写成此次新增 |
| Test Repair 补丁校验 | 不可变文件/coverage、受控 AST 改动、全量复验 | 允许的唯一具体改动由两个固定证明器定义 | 保守未决而非强行修坏其他 Contract |
| Challenge 违规见证 | Contract 审查、合法域、执行见证、正确对照、两次评分、产物一致性 | 固定观察 DSL 和示例路径；非 CSV 无专用算法分支 | 可迁移；非 CSV 自主成功率仍需动态验证 |
| Reviewer 独立性 | 独立 messages，不提供参考源码/结果 | 可复用同一 client/model；不是外部独立审查者 | 无 CSV 语义硬编码；相关误解风险待评估 |
| Controller 状态转换 | 证据完整性、面板充分、后端一致、未决阻断 | 没有 email/CSV/字段专用条件 | 可原样复用；静态上游误拦会间接阻止接受 |

最近 Synthesis/Test prompt 中新增“instruction 不得超出 Contract（包括行尾和域外行为）”本身是通用约束，不是要求生成 CSV。API transport/预算调整按请求与错误类型处理，未见任务格式或 CSV 字段参与分支；本次不把网络重试策略作为任务无关性缺陷扩展审计。

## 6. 最小必要改进清单（未实施）

| 顺序 | 最小改进 | 对应证据 / 目的 |
|---|---|---|
| 1 / P1 | 通用层保留附录校验；CSV 语义规则显式启用并区分 input/output；增加两条误拦回归 | F01，先消除合法任务被拒绝 |
| 2 / P1 | 为主机证明器暴露能力判断，把 literal/JSON 特例从通用函数分支移入可配置适配器，unsupported 提前未决 | F02，明确哪些任务能自动修复；不放松授权 |
| 3 / P1 | 对违规实现通过的诊断，按映射附上有界测试源码和 Contract 见证；无可定位证据时显式不足 | F03，使非 JSON 样例获得同等诊断信息 |
| 4 / P2 | 一个一致的运行 profile 声明，列出 Python、布局、pytest、文本/fixture 类型、观察操作符、资源上限 | F04–F06、F12，避免“任意 Terminal-Bench”误解 |
| 5 / P2 | 验收报告分开展示实验 passed、历史回归和 Controller accept | F11，防止把实验成功当成完整独立接受 |
| 6 / P2 | 用现有 JSONL/manifest 先补三段独立验证：生成、一般测试缺陷修复、Challenge 增补；复用已有冻结数据 | F02、F07、F10、F13，证据缺口按阶段补齐 |

不建议在此次审计后立即泛化所有语言、放开任意 Dockerfile、接受模型自行授权、删除 holdout 门禁或把 CSV 换成更多字符串特判。上述改进可以保持现有框架与安全边界。

## 7. 本次验证及仍需动态验证的假设

实际执行的少量离线测试：

```bash
PYTHONDONTWRITEBYTECODE=1 .harbor-venv/bin/python -B -m unittest \
  tests.test_instruction_consistency.ConsistencyTests \
  tests.test_json_attribution.JSONAttributionTests \
  tests.test_implementation_library.SemanticTests \
  tests.test_controller.DecisionTests -v
```

结果：**29 tests，全部通过，0 skipped，0 failed**。分别验证现有 drift 门禁与一次诊断、JSON 窄证明及补丁范围、CSV/JSON/manifest 有限语义与边界、Controller 证据和状态规则。没有运行 DockerRegression、模型验收模块或 full discover。现有测试通过并不能排除本次新构造的 F01/F03 场景，二者未写入项目测试。

额外执行的纯函数检查：六规格 `default_specs/validate_inputs`；六个 Contract 的同文 instruction 检查；六个 Contract 的 `json_attribution.supported` 与 `_assertion` 前置条件；F01 两个输入域行尾误拦；F03 的 invalid-outcome 包；读取库 entries 和 RESULTS 的 19 套评分摘要。未执行被测实现或生成的测试代码。

仍需单独授权范围下的动态验证（此次未运行）：

- **生成可迁移性 D**：JSONL、manifest 及完全新领域，从新 Plan/Contract 生成现实初始错误、参考解法、独立测试，能否遵守各自字段、顺序和交付规则；人工夹具不能替代此证据。
- **修复可迁移性 D**：分别注入过严序列化、遗漏字段、错误分组及 fixture 缺陷，区分“已知不支持的主机规则”和“模型没诊断出问题”；先修 F02/F03 再测自动闭环。
- **Challenge / Reviewer D**：新 JSON 与文件系统任务中，能否自主找到可复现漏检，Reviewer 是否接受等价序列化而拒绝域外输入；用同模型/异模型配置比较相关误解。
- **观察器边界 D**：二进制、CRLF 精确字节、目录元数据等 Contract 是否需要扩 DSL；当前静态可知无法完整表达，不假设存在通用降级路径。
- **资源 D**：较大的但仍合法输入、大量独立测试、目录产物、多模块程序在 Docker/Harbor 是否因固定预算表现不同。
- **验收 D**：使用新 Contract 的真正四类审查面板，验证 Controller accept；另测 E2E `passed` 与 Controller 未决是否被 UI/调用方混用。不能以原始库摘要代替当前工作区的完整执行验证。

## 8. 最终回答

**如果明天仅提供一个全新的非 CSV Terminal-Bench Plan 和 Contract，现有系统不能保证不改核心源码就自动跑到 Accepted。**

如果它属于现有 Python 标准库、`/app`、Linux Docker CLI 修复方向，**可以不改核心代码启动生成、生成测试和执行验证**；JSONL 与目录摘要并不存在必须改成 CSV 才能运行的全局条件。但“仅换 Plan/Contract 就自动完成”具体卡在：

1. 超出该方向时，`validate_inputs` 直接拒绝；这首先是明确支持范围的问题。
2. 符合方向仍需新的、绑定 Contract 的独立对照及审查证据；没有这些，Controller 不会正式接受，现有六任务 recipe 不能解释任意新 Contract。
3. 若首轮测试存在一般缺陷，普通 Test Repair/Dispatcher 只支持两个样例证明器，通常停为 `needs_review`；目前增加新证明能力还需修改核心分派，单换 Plan/Contract/数据不够。
4. CSV 专用一致性规则有可能误拦合法非 CSV instruction；一般漏检诊断又可能缺少源码。这是已确认的通用层兼容性问题。
5. Challenge 有更通用的增补路线，但受观察 DSL、独立审查和预算限制，尚无本次范围内的动态证据证明任意新任务可自主成功；它也不替代完整独立面板。

因此准确定位是：**多任务执行与控制骨架可复用，有限题型适配器有效；任意新 Contract 的语义检查、独立证据构造和自动测试修复尚未通用化。**
