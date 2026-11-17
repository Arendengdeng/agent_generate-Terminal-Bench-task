# 任务无关性改进复审

日期：2026-11-16。范围：当前工作区 F01/F02/F03 的实际实现、调用路径和离线回归，并检查 Challenge 增补通路是否保持兼容。

本次不修代码，仅新增本文档；没有真实模型调用、任务生成、容器执行或完整 Pipeline 运行。模型流程探针使用 ScriptedClient，sandbox 使用 Mock；所有新增例子只供静态解析，不执行其中的测试/任务源码。原始 `task_agnostic_audit.md` 保留为改进前的审计记录。

## 判断

**明显改善，但总体仍是“部分通用”。主要进步是默认通路不再自动施加 CSV 语义，且明确不支持的证明规则能提前、零模型预算地保持未决；没有新增任意 Contract 的自动证明能力。**

| 项目 | 改进前 | 当前证据 | 复审结论 |
|---|---|---|---|
| F01 CSV 规则进入通用层 | 文本含 csv 即触发，输入规则可能按输出判断 | Config 默认空规则；显式选择；原两个误拦回归通过 | 核心耦合已解除；可选规则仍有措辞误拦 |
| F02 不支持证明规则浪费预算 | 通常先模型诊断，再发现无主机证明规则 | workflow、Dispatcher、TestAgent 普通诊断/修复都有能力门槛；六种现有 Contract 的零调用回归通过 | 大幅改善；能力检查尚未绑定本次失败 |
| F03 违规实现通过时无源码 | 没有 traceback 或 JSON 特例位置就没有源码 | 依 Mapping 提取函数、静态 helper/fixture 和引用数据；有字节/行数上限及局限标记 | 原缺口已补；隐式 fixture 依赖仍不完整 |
| Challenge 增补修复 | 独立见证 → Reviewer → Controller → 增补测试 | 不走普通证明器门槛，相关离线回归通过 | 未发现本轮改动破坏该通路的证据 |
| 接受和隔离机制 | Controller、独立面板、Docker/Harbor | 对照 HEAD 检查，Controller、Docker runner、Harbor、Challenge workflow 无源码差异 | 没有放宽接受标准或隔离机制 |

## 已确认的改进

### F01：默认通路已经摆脱 CSV 自动识别

`synthesis_agent/config.py:29` 的 `consistency_rules=()`；`synthesis_agent/consistency.py:9` 默认只做附录检查，规则必须作为参数显式传入，没有 `csv in input_spec/output_spec` 的启用分支。

配置沿 `candidate.check_candidate`、`exporter.load_tests`、`pipeline.verify`、Dispatcher、Test 输入及证明检查传递。`synthesis_agent/format_rules.py:36` 分别维护 input_spec/output_spec 的授权集合，不再把所有 instruction 行尾都当成输出约束。

原审计中的两例已有回归：`tests/test_task_agnostic.py:54` 非 CSV 描述“不是 CSV”加输入 LF，以及 `:61` CSV 输入 CRLF。两者本轮再次通过。默认不启用规则，也意味着历史 CSV 漂移不会默认被语义检查拦住；这是显式选用的设计结果，不应把 `no_findings` 宣称为语义一致。

### F02：证明器与一般调度已经分离

`independent_verification/repair_proofs/` 分别存放 literal stdout 和 JSON doubling 证明器；`attribution.py:14`、`:19` 负责通用分派，保留最终严格诊断/补丁校验。`diagnosis.py:14`–`:18` 在模型之前拒绝无适配器或没有可识别断言形态的任务。

`test_repair_workflow.py:67` 在 `agent.analyze` 之前准备反馈；`repair.py:185` 先保存未决执行问题，再在 `:191` 检查能力；`agent.py:303`–`:309` 也对直接调用普通诊断/修复的情况提前返回。Unsupported 不会计成 repairs，也不会变成成功。

六种现有 Contract 仍不属于这两个窄证明域，但目前会零模型调用停为 `needs_review / unsupported_proof_rule`。这改善了失败成本和状态准确性，**并不说明这六种 Contract 现在能自动修复一般测试缺陷**。

### F03：普通漏检已有有界源码证据

`diagnosis.py:44` 选择 completed、expected_reward=0、reward=1 的反馈违规实现；`:98` 按相关 Requirement Mapping 定位测试。没有具体违规 Requirement 标记时，明确在预算内使用全部映射，而非编造一个违规归因。

`diagnosis.py:118` 的静态提取覆盖函数参数引用的 fixture、helper、常量、导入、装饰器及能识别的数据文件引用；`:55` 限制源码总字节数和单片段行数，并在截断时记录局限。`:29` 同时检查 trials/evidence 的 holdout 标签；包中不恢复完整执行日志。这些已有针对性回归通过。

## 本次额外复现的三个残余问题

以下均为 **P2**：会误拦、浪费一次诊断或使诊断不完整；未发现因此绕过严格补丁验证或错误 Accepted 的证据。本次不修改代码。

### R01 — 可选格式规则仍会把无法归属的 Contract 条款当成没有授权

**分类：B 中的局部缺陷；对应 F01。**

证据：`synthesis_agent/format_rules.py:20` `scope` 看到同一分句有“输入”和“输出”即返回 None，`:40` 跳过该 Contract 条款；之后 `:57` 又把未提取到授权作为阻断 instruction 的依据。

本次纯函数复现，在 CSV Contract 的 output_spec 中使用：

```text
UTF-8 CSV，空输入输出仅有表头，行尾使用 LF。
```

instruction 为 `输出行尾使用 LF。`，显式启用 `csv-line-endings`。实际结果是 `blocked / UNSUPPORTED_CSV_LINE_ENDING`。Contract 已在 output_spec 声明 LF，只因“空输入”措辞同时含输入和输出，授权被丢弃。

影响范围：仅显式启用该可选规则时；没有恢复原来的默认全局 CSV 耦合。最小建议：区分“没有声明限制”和“声明存在但作用域无法解析”；后者应报告未能验证，不能直接推出 instruction 额外加义务。补此类边界回归。

### R02 — capability 是套件中存在受支持形态，不是本次失败存在可证明修复

**分类：D 的能力边界已实证；对应 F02。**

证据：`repair_proofs/__init__.py:14` `repair_capability` 不接 execution；`:27`–`:37` 遍历所有 Assert，只要某条能被 adapter.assertion 识别即令 eligible=True。它没有判断当前失败是否就在该断言，也不检查该断言是否已经符合 Contract。

本次离线探针使用合法的 Print-42 Contract，测试中同时放入：

```python
assert result.returncode == 99  # 当前失败位置；不属于 literal stdout 补丁规则
assert result.stdout == b'42\n'  # 已经正确，但属于可识别形态
```

执行反馈的失败位置指向 returncode 断言。实际结果：capability.supported=True；TestAgent.analyze 调用了 ScriptedClient 一次，最后 needs_review，sandbox.prepare 未调用。没有真实模型费用，但已证实这条路径仍会到达模型请求。

因此，上轮“无证明器提前零调用”的结论仍成立；但“所有不支持的失败形态都零调用”过强。严格主机证明器仍会拒绝修补不支持的 returncode 断言，不是授权漏洞。

最小建议：保持 Contract/AST capability 作为第一层筛选，再增加针对当前 execution 的 proof-candidate 发现；如果现有适配器能确定所有相关失败均不在证明域，模型之前返回 unsupported。对只能证明源码形态、不能证明当前失败的情况，报告能力范围，不把它当作“此次可修复”。

### R03 — 源码提取未包含 statically-declared autouse fixture

**分类：D 的静态提取边界已实证；对应 F03。**

证据：`diagnosis.py:158` 从映射根开始，仅跟随 Name、函数参数和字符串引用（`:168`–`:178`），没有枚举 `@pytest.fixture(autouse=True)` 作为隐式依赖。

本次纯函数探针：映射测试为无参数的 test_output；同一模块中声明 autouse setup_paths，修改工作路径环境。生成的包只有 test_output 的源码，没有 setup_paths。输出包含通用的 `static_dependencies_only`，但未定位这个静态可识别的遗漏。

影响：这类 fixture 可能决定测试环境或输入，其缺失会令“必要上下文”不完整。不是所有 fixture 都失效；通过参数引用及静态字符串引用的 fixture 已有回归通过。

最小建议：把模块级 autouse fixture，以及适用于映射测试的静态 usefixtures 标记纳入依赖闭包，并继续受现有源码预算限制。无法解析的动态引用仍应保留未决。

## 验证结果与证据强度

重新执行上轮相同的 83 项定向离线测试：**83 passed，0 failed，0 skipped**，耗时约 3.9 秒。范围包括 task_agnostic、instruction consistency、JSON attribution、RepairTests、三项 Dispatcher 定向测试、CSV/JSONL/manifest SemanticTests、ChallengeTests、Controller DecisionTests。`git diff --check` 通过。

另运行上述三个只使用静态字符串、纯函数或 ScriptedClient/Mock 的探针；它们不在这 83 项原有回归内。测试通过与新边界复现并不矛盾：原有测试尚未覆盖 R01–R03。

没有重新运行真实模型闭环，没有运行 Docker/Harbor 评分，也没有据离线 Stub 的 passed 状态声称一个任务 Accepted。当前结论是接口与控制逻辑的离线验证，模型成功率和跨任务自主修复能力仍需另行验证。

## 最终回答

**是，确实比上次更好了。** 默认框架已不再根据 CSV 文字猜测任务格式；无适配器任务会明确、低成本地停下来；普通漏检也能获得更多任务无关的源码证据。

但这次主要提升了边界清晰度、失败成本和诊断可用性，未扩展自动证明域。一个新非 CSV 任务在现有 Python CLI profile 内仍可不改核心代码启动生成与执行；若要求自动修复一般测试缺陷并最终 Accepted，仍需适用的证明适配器、完整独立面板及成功执行证据。当前不能保证仅换 Plan/Contract 即自主跑通。
