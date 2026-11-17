# 核心实现提炼计划与审计依据

基准为 master/c8be56d + 本次开始时的dirty源码。原目录及所有未提交文件保留；不stash、不reset、不clean、不改写已有提交、不push。审计报告和原始证据仍在原目录 reports，核心分支只保存必要文档和本次验证结果。

## 保留范围

|内容|选择|原因|
|---|---|---|
|synthesis_agent 顶层全部.py|保留，含未提交consistency/client改动|模型协议、输入校验、FileSet、Docker、自检与修复是核心|
|independent_verification 顶层全部.py|保留，含未提交diagnosis/受限诊断改动|Controller、两种修复、Challenge/Reviewer、panel、双后端、通用e2e/robustness均有真实机制|
|candidate_batch/specs.py、controls.py|保留小适配层，明确不是batch入口|现有诊断/回归测试使用；保留接口与规范派生不引入另分支未整合runner|
|examples/csv、jsonl、manifest Plan/Contract|保留|测试和三题型最小输入依赖|
|单个真实CSV冻结candidate+测试|保留清单内文件、必要metadata及来源说明|让inspect/export/Docker评分无需模型可复现；不复制私有日志|
|核心tests及helpers/fixtures|保留；删implementation_library专用test|验证真实核心控制与边界；测试里的scripted模型明确只用于验证|
|scripts/challenge_agent/run_acceptance.py、run_e2e.py|保留|前者被核心测试导入，后者是通用真实验收入口；构造初始suite明确标人工|
|scripts/independent_controls/run_experiments.py|保留|核心测试依赖其中真实场景构造/JSON测试函数；不伪装生产Planner|
|pyproject、requirements-verification、.env.example|保留|最小安装和固定Harbor/pytest版本；不复制.env|

## 排除范围

- runs、step3_test_1112、archives、evaluation_library 的海量历史产物和重复source快照：报告在原目录索引，不放进核心tip。
- independent_verification/implementation_library 及其评估脚本/专用测试：是研究评估支路，普通核心verify/repair/challenge不依赖。
- scripts固定9/24快照、CSV专用历史adapter、旧build_report等：依赖原历史路径或只生成报告，不属通用执行链。
- 旧repair_dispatcher_acceptance.py：当前严格panel语义下只传path无法授权，使用现有RealDispatcherTests的已审查面板作为真实复验，避免保留已过时成功脚本。
- 另分支candidate_batch/runner.py与__main__.py：不会悄悄合并另一套Pipeline；当前master缺口如实文档化。
- 退役validation stash源码：已审计机制与恢复定位，不构造假集成。
- venv/egg-info/cache/.env/密钥、旧README与历史设计报告：新README/docs针对核心实际行为重写。

## 执行和提交

先检查分支/路径冲突；目标agent-core-initial，worktree置于相邻agent-core-initial目录。仅从初始HEAD建分支。复制保留的dirty文件/新文件后核对SHA256；保留复制清单。新worktree中按allowlist精简tracked文件；不使用git reset --hard或git clean。测试使用已有Harbor Python绝对路径，不复制venv；--harbor-python/HARBOR_PYTHON显式指向它。默认离线回归、CLI帮助、真实冻结示例inspect/export/Docker、opt-in沙箱/Repair/Challenge测试均记录exit code。模型真实生成不额外运行，复用已审计历史；本次scripted+真实Docker只证明机制，不声明真实模型性能。

提交前检查git diff --check、完整staged文件与diff、意外秘密路径/内容，不stage原工作区。独立提交，最终记录branch/worktree/hash/统计及测试限制。删除产物不删除共享历史。

## 执行结果

- 分支：`agent-core-initial`；worktree：`/home/zyl/projects/agent-core-initial`。
- 独立提交：`6e0bfa2562273770c6e98a7e5bc6ec8a14c52976`；parent为原HEAD `c8be56df1999db8b728644770242652fe677a2d0`，未push。
- 原HEAD仍是master/c8be56d，源文件hash比较无变更；核心worktree clean。保留69份原核心源码/测试/配置文件的复制hash，最终tip120个tracked文件、900835 bytes。相对parent的commit为419 files changed、3750 insertions、64712 deletions（含Git自动rename识别）。
- 默认回归224项：209通过、15跳过；额外真实容器集成10项全部通过，均为零API/scripted模型；冻结14-node CSV Oracle=1/Nop=0，独立验收false。
- Print42 Dispatcher真实Docker/Harbor终验与offline review均accept，1轮修复；六冻结实现结果一致。严格Harbor no-network probe exit1/unsupported，未将public当严格通过。
- [完整命令/退出码](../runs/archive/audits/workspace-architecture-20261116/core-validation/commands.json)、[机器结果](../runs/archive/audits/workspace-architecture-20261116/core-validation/results-summary.json)、[staged审查](../runs/archive/audits/workspace-architecture-20261116/core-staged-review.json)、[分支记录](../runs/archive/audits/workspace-architecture-20261116/core-branch.json)。
- diff检查最初提示CSV字段尾空白；这是实际行为fixture，不可删除。新增.gitattributes仅对冻结CSV夹具路径关闭whitespace风格诊断，其余保留检查；最终staged diff检查通过。未为通过检查改变夹具字节。
- 单个冻结示例保留历史真实文件与必要metadata，公开元数据裁剪和provenance明确；未增加假Agent。README/ARCHITECTURE/CORE_SCOPE/VALIDATION已在核心commit。
- 运行使用原项目已有Harbor解释器绝对路径；venv未复制。完整容器原始证据留core/runs（忽略、不提交），文件清单见[core-run-artifacts.tsv](../runs/archive/audits/workspace-architecture-20261116/core-run-artifacts.tsv)。
