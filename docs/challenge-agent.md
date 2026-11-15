# Step 4 · P1：Challenge Agent 说明

## 目标与验收标准

Challenge Agent 主动寻找评分漏洞，而不是重复运行固定的错误实现面板。

输入为 Contract、Instruction、初始环境和冻结测试；输出为候选错误实现、独立违规证据、冻结测试评分和 Controller 决策。验收要求至少发现一个真实误通过漏洞，补测后同一错误实现正常断言失败，同时 Oracle 与已知正确替代实现通过。

当前实现支持完整流程和四组实验。**真实模型完整闭环尚未验收通过**；阶段结果见文末，不应将脚本化测试或“代码已接通”等同于验收完成。

## 职责边界

|组件|负责|边界|
|---|---|---|
|Challenge Agent|读取公开输入及冻结测试，主动编写候选解法、提出见证并利用执行反馈继续搜索|只允许写 `solution/`；不能修改测试、Contract、Verifier 或评分规则；不能读取参考解法|
|独立见证审查|依据 Contract 审查输入合法性和预期断言的规范依据|独立对话；不提供评分测试、候选源码、Oracle 输出或评分|
|受信执行器|在独立 Docker 环境运行见证和评分，记录观察及一致性检查|模型生成代码不在宿主机执行；任务容器不接触评分测试|
|Controller|检查违规与误通过证据，排查基础设施问题，决定补测或复核|满分本身不能直接归因为测试漏检|
|Test Agent|根据 Controller 确认的缺失行为断言增加通用测试|Challenge 路径只允许增补，原测试和 fixtures 保持原样|
|Pipeline|执行阶段编排、派发与回归|不把 Agent 的自报结论当作已确认漏洞|

## 流程与状态

1. 校验候选及冻结测试的输入绑定、文件清单、摘要和 Requirement 映射，执行基础对照。
2. Challenge 读取测试及初始环境，针对 Requirement 主动生成带 `solve.sh` 的候选解法。
3. Challenge 提交独立行为见证；独立审查确认每条预期断言可由 Contract 推导。
4. 在隔离环境中执行同一见证：候选违反断言，Oracle 和已知正确实现满足断言，才能确认违规。
5. 将该候选在原冻结评分套件中运行两次，检查实现、测试、文件传递和评分一致性。
6. Controller 只有在确认违规、稳定误通过且基础设施检查通过后，才派发测试修复。
7. Test Agent 增补测试；独立审查检查是否为通用 Contract 行为测试。
8. 完整运行全部对照，复验独立见证，并执行 Harbor 最终评分。

|状态|含义|
|---|---|
|`unconfirmed`|无法证明违规、规范有歧义，或见证拒绝正确对照；不进入已确认错误样本|
|`error`|见证、评分或基础设施执行异常；不能算违规或正常拒绝|
|`rejected`|已确认违反 Contract，但冻结测试已经正常拒绝；不是误通过漏洞|
|`confirmed`|已确认违反 Contract，冻结测试两次误通过，Controller 批准补测|
|`resolved_docker`|修复后的 Docker 对照通过；仍需最终 Harbor 验收|

`violation_status` 与漏洞状态分别记录。已确认错误实现可以被原测试拒绝，并不一定构成评分漏洞。只有最终 Harbor 中错误实现失败且正确对照通过，普通 Pipeline 才设置 `challenge_resolved=true`。

未确认及异常样本进入 `review_queue`，保留原因和证据路径。人工复核应另存意见，不应直接编辑自动确认状态。

## 独立行为见证

见证单独保存，不属于待评估的 Test Agent 评分套件。结构如下：

```json
{
  "requirement_id": "R1",
  "contract_quote": "Print 42 and exit successfully.",
  "rationale": "R1 明确要求无输入时成功退出并输出 42。",
  "argv": ["python3", "/app/clean.py"],
  "stdin": "",
  "fixtures": {},
  "assertions": [
    {"source": "exit_code", "path": [], "value": 0},
    {"source": "stdout", "path": [], "value": "42\n"}
  ]
}
```

第一版断言采用确定性相等比较，支持：

|`source`|`path`|行为|
|---|---|---|
|`exit_code`|`[]`|退出码等于预期整数|
|`stdout` / `stderr`|`[]`|输出文本等于预期文本|
|`json`|字段名或数组索引列表|stdout 解析后的 JSON 指定位置等于预期值|
|`file`|相对文件路径|临时工作目录中的文件内容等于预期文本|
|`unchanged`|输入 fixture 的相对路径|输入内容未变，`value` 为 `true`|

fixtures 在独立临时目录创建，命令参数中的 `$WORK` 指向该目录。无法表达的行为不自动确认。观察记录包含实际退出码、stdout/stderr、逐条断言的实际值及失败信息。

Oracle 与正确替代实现用于检验见证是否误拒，**它们与 Challenge 输出不同本身不是违规证据**。独立模型审查也不是形式化证明，其规范推导和不确定性必须保留供复核。

## 误通过归因与修复约束

评分器及归因检查覆盖：

- 实际实现与提交候选的摘要一致。
- 评分套件、收集到的 node IDs、setup/call/teardown 记录与冻结版本一致。
- pytest 退出码、原始结果、评分解析结果及 reward 一致；error/null 不计作正常拒绝。
- 任务环境导出的产物与评分环境收到的产物摘要一致。
- Verifier 文件在执行前后保持一致。
- 两次全新环境评分均误通过，且产物摘要与独立见证运行一致。

发现异常时，停止测试修复并保留基础设施调查证据。检查通过是当前链路的一致性证据，不代表证明 Verifier 没有任何漏洞。

修复要求保留原测试和 fixtures 的全部内容，只增加测试文件及必要 fixtures，保留旧 node IDs。独立补丁审查拒绝源码检查、实现身份或摘要特判、跳过测试、修改评分以及新增 Contract 未要求的行为。

修复后的完整套件须覆盖 Oracle、Nop、已知正确实现、用户提供的错误对照及全部已确认 Challenge 错误样本。独立见证也需重新执行。正确实现失败、错误样本仍通过或执行异常，均不得宣称修复成功。

## 普通运行

运行前需准备 Python 3.11+、Linux Docker、任务镜像、`independent-verifier:pytest-9.2.0`、Harbor 0.25.0，以及模型配置。模型沿用 `SYNTHESIS_MODEL`、`SYNTHESIS_API_KEY` 和可选 `SYNTHESIS_BASE_URL`；生产 CLI 不自动加载 `.env`。

```bash
# all 默认开启独立测试、Challenge 和有界测试修复
python3 -m independent_verification \
  --candidate runs/task --output runs/verification \
  --known-correct runs/correct-alternative

# 对已有冻结测试主动挑战
python3 -m independent_verification --stage run \
  --candidate runs/task --tests runs/independent-tests \
  --challenge --known-correct runs/correct-alternative \
  --output runs/challenge-verification

# 显式关闭 Challenge 和测试修复
python3 -m independent_verification --stage run \
  --candidate runs/task --tests runs/independent-tests \
  --no-challenge --no-repair-tests --output runs/scoring-only
```

默认最多评估 4 个候选，可使用 `--max-challenge-attempts` 调整。按 Requirement 轮转目标，候选可根据反馈迭代。生成、独立审查和修复共享模型及工具预算；测试修复最多 2 轮，基础修复已使用的轮数会扣除。

`all --no-repair-tests` 需要同时指定 `--no-challenge`。`inspect/generate/export/decide` 不启动 Challenge。现有跨模块 `--repair` 是独立流程，不能与显式 `--challenge` 组合。

## 四组对照实验

实验入口必须显式选择 `--experiment`，覆盖普通 `all` 的默认开关。

|组别|行为|比较目标|
|---|---|---|
|`baseline`|使用显式提供的冻结原始评分套件；不生成、不挑战、不修复|原始评分能力|
|`independent`|生成独立测试后冻结；也可传入已生成套件回放|独立测试的贡献|
|`challenge`|使用 Independent 的同一冻结套件；主动搜索但不修复|主动发现的已确认误通过漏洞|
|`repair`|复用 Challenge 的实现和证据，在原套件上补测；不重新搜索|修复贡献及正确实现回归|

Baseline 必须提供 `--baseline-tests`。它可为明确标注的人工基础套件，但必须具有现有 `tests.json`、文件摘要、输入绑定、node IDs 和映射，不能将 Synthesis 自检冒充独立评分。

```bash
python3 -m independent_verification --experiment independent \
  --candidate runs/task --known-correct runs/correct-alternative \
  --output runs/exp-independent

python3 -m independent_verification --experiment challenge \
  --candidate runs/task --tests runs/exp-independent/independent-tests \
  --known-correct runs/correct-alternative --output runs/exp-challenge

python3 -m independent_verification --experiment repair \
  --candidate runs/task --tests runs/exp-independent/independent-tests \
  --challenge-report runs/exp-challenge/challenge/challenge-report.json \
  --known-correct runs/correct-alternative --output runs/exp-repair

python3 -m independent_verification --experiment baseline \
  --candidate runs/task --baseline-tests runs/baseline-tests \
  --challenge-report runs/exp-challenge/challenge/challenge-report.json \
  --known-correct runs/correct-alternative --output runs/exp-baseline-replay
```

对 `independent` 再传入原套件和 `--challenge-report`，即可回放同一批已确认错误样本。四组必须共用任务、初始环境、正确对照和评分设施；非 Repair 组的套件摘要不得变化。

`experiment.json` 分别记录组别、开关、测试摘要、误通过率、误拒率、异常数和调用成本。无错误样本时误通过率为 `null`；异常另计，不能解释成拒绝成功。Challenge 发现的样本带有选择效应，不是独立保留集上的稳健性证据。

## 产物与实现入口

|位置|内容|
|---|---|
|`challenge/frozen-tests/`|搜索前冻结测试副本|
|`challenge/search/trace.jsonl`|主动搜索及独立审查的脱敏工具轨迹|
|`challenge/search/candidates/<id>/solution/`|候选错误实现|
|同目录 `witness.json`、`review.json`、`observations.json`|规范依据、独立审查、实际行为和违规断言|
|同目录 `scoring-0/`、`scoring-1/`|两次评分、pytest 结果和实现／产物清单|
|同目录 `evidence.json`、`decision.json`|误通过证据与 Controller 决策|
|`challenge/repair/`|测试修复、差异、补丁审查和各轮完整对照|
|`challenge/final-witness/`|修复后独立见证复验|
|`challenge/challenge-report.json`|样本状态、复核队列、对照矩阵、预算和证据哈希清单|
|`run_result.json`、`decision.json`|最终 Harbor 验收与 Controller 总体结论|

实现入口：`independent_verification/challenge.py`、`challenge_workflow.py`、`challenge_experiment.py`。Controller、Docker 评分器、Test Agent 和 Pipeline 提供相应接入。

普通 Pipeline 的离线 `decide` 会重读 Challenge 报告，检查摘要、输入绑定、Controller 归因及最终 Harbor 是否包含并拒绝了错误样本。

## 验证与当前状态

```bash
python3 -m unittest discover -s tests -v

CHALLENGE_DOCKER_TESTS=1 python3 -m unittest \
  tests.test_challenge_agent.RealDockerWitnessTests -v

python3 scripts/challenge_agent/run_acceptance.py \
  --output runs/challenge-acceptance-NEW \
  --env-file /path/to/existing/.env \
  --harbor-python /path/to/harbor-venv/bin/python
```

真实验收脚本使用人工定义、语义明确的任务及正确对照，真实 Test Agent 生成独立测试，真实 Challenge 模型生成错误实现，真实 Test Agent 修复。错误实现不预置。源码快照、协议、完整组别结果和首次失败均保存于输出目录。

截至本次文档生成：

- 最近一次完整离线回归运行 95 项，其中 86 项通过、9 项跳过；新增 Challenge 控制流测试通过。
- 一项真实 Docker 测试通过，确认独立见证与冻结评分可得出不同结论；该项候选由脚本提供，只证明执行与证据链路，不能替代主动发现验收。
- 首次真实运行因模型批量工具调用与协议不匹配停止，失败记录保留在 `runs/challenge-acceptance-01`；协议已修正。
- 第二次真实运行完成了独立测试和 Challenge 评分。一个候选未确认违规，另一个已确认违规但被原测试正常拒绝；尚未发现满足验收标准的误通过漏洞，因此没有宣称完整修复闭环通过。记录保留在 `runs/challenge-acceptance-02`。

本次 P1 的最终验收仍需补齐：真实模型主动发现误通过漏洞 → Controller 确认测试缺陷 → 通用补测 → 同一错误实现失败且正确对照通过 → Harbor 验收通过。
