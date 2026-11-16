# Core Scope 与来源

## 来源及保留原则

从原master/c8be56d创建agent-core-initial独立worktree，复制审计时核心未提交改动，保留原开发目录全部修改。没有合并另一分支、恢复stash、改写旧提交或push。删除仅作用于新tip，共享历史仍存在。

保留两生产包顶层：Synthesis、client/config/文件/沙箱、Contract/有限一致性，Candidate/Static/Test/诊断/宿主proof、普通loop和Dispatcher、Challenge/Reviewer、panel、Docker/Harbor适配、通用e2e/robustness。它们构成实际执行机制，不只保留一个生成器。

`candidate_batch/specs.py/controls.py`作为小型规范/对照构造适配层保留：部分核心测试使用。master没有runner/__main__；本分支不增加它们，也不声称支持批量生产入口。

保留三个真实Plan/Contract族、核心unittest和所有相关新fixture/client可靠性测试；脚本保留通用Challenge验收和核心测试依赖的independent_controls场景构造。人工构造初始suite和scripted模型始终标注来源，不作为真实模型成功。

## 新纳入的原未提交修改

- `synthesis_agent/client.py`等：每尝试异常链、typed重试、usage未知标志、保守token预留；全局calls计数。
- `synthesis_agent/consistency.py`与candidate/Test/归因调用：有限Contract–Instruction gate。
- `independent_verification/diagnosis.py`及Test/repair workflows：定向证据包、只读单次诊断、上下文和completion上限。
- `tests/test_client_reliability.py`、`test_instruction_consistency.py`、`csv_drift_fixture.py`及JSON fixture，以及原dirty回归修改。

这些修改逐文件从原工作区复制，hash核对。没有忽略尚未提交实现，也没有改变原工作区以便提交。

## 单个完整冻结示例

`examples/frozen-csv/candidate`来源`runs/archive/candidates/acceptance-csv-01`；`test-agent`来源`runs/p0-fixed-panel-manual-20261115-013144/verification/test-agent`。保留原文件内容、Contract/Plan、自检、必要公共metadata/manifest/nodeids；不复制私有trace、旧absolute log paths或API配置。provenance.json标明来源和每文件hash。

这是历史真实模型生成任务+独立测试，可离线inspect/export和零模型真实Docker评分。14-node suite在历史9/24面板仍漏检5个、有2个error，本示例不声称Validated Benchmark或Accepted。示例脚本不改变生产接受门槛。

## 排除及原因

|排除|原因/可恢复性|
|---|---|
|runs、step3_test_1112、archives、evaluation_library|海量历史制品、重复source和固定回归材料；原目录reports完整索引|
|implementation_library包、专用测试/脚本|独立评估支路，普通生成/验证/修复/挑战不依赖|
|CSV历史adapter、固定9/24快照脚本和build_report|依赖原历史路径、只做结果整理或重复驱动|
|旧repair_dispatcher_acceptance.py|不符合当前严格panel输入；保留当前RealDispatcherTests作为真实集成入口|
|原README/docs历史大集合|新文档只描述核心实物，研究报告保留于原目录reports|
|退役validation package/stash|当前不集成，恢复会造成假支持；Git stash证据在原报告解释|
|另分支batch runner|未完整合入master，不能悄悄扩大提炼范围|
|.env/keys/venv/egg-info/cache|本地私有或可重建，不参与核心源码交付|

冻结CSV夹具包含必须保留的字段首尾空白；.gitattributes仅对该夹具路径关闭whitespace风格诊断，避免为diff检查改坏真实测试数据。其他文件仍执行git diff --check。

本分支新增的只有核心文档、固定verifier构建文件、小配置样例和零模型冻结示例驱动脚本，以及上述数据属性；没有假Agent实现。生产Python源码保持复制来源hash不变。

## 尚未验证与设计状态

自动Planner/Solver/难度/正式数据集Missing；通用CSV语义归因Missing；Reviewer形式正确性Unverified；完整真实模型自动闭环稳定性Unverified。真实Docker/Harbor验证结果见VALIDATION，scripted+容器成功只证明接口/调度/执行机制，模型历史证据在原审计报告中另列。
