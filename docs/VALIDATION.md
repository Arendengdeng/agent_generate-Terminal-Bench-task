# 本次核心提炼验证

验证运行于提炼worktree，解释器为原项目已有Python3.12 Harbor环境的绝对路径，没有复制venv。源码来自c8be56d加审计时dirty核心；生产包复制后hash未变化。**本次真实模型API调用为0**。scripted client只提供预定义工具消息，Docker、pytest、Harbor与宿主归因/补丁门槛是真实执行。

|检查|结果/退出码|范围|
|---|---|---|
|默认unittest|224项，209通过，15按opt-in跳过；0|排除独立实现库的21项专用测试，保留核心回归|
|AST语法+Import|0|两生产包、scripts/tests语法与关键模块导入|
|两CLI --help|均0|Synthesis与Independent Verification|
|真实冻结CSV离线inspect/export|0|3文件/14nodes独立套件，当前candidate输入和摘要绑定|
|Docker/Harbor preflight|0/0|Linux Docker可用，Harbor0.25.0|
|沙箱+Synthesis自检|5项通过；0|网络/文件/身份隔离、超时与输出溢出清理、链接、probe错误分类、scripted生成真实自检|
|独立执行与测试修复|3项通过；0|4对照真实执行与一次修复、非法artifact/失败solve保留error、目录/二进制转交|
|Challenge独立见证|1项通过；0|scripted错误候选在真实见证和冻结评分产生不同结果；不是自主模型发现|
|Dispatcher+Harbor|1项通过；0|Print42缺陷断言43→42，宿主确认、1轮修复、全量终验及offline review均accept|
|真实冻结CSV Docker|0，Oracle=1/Nop=0|零模型Oracle/Nop，局部baseline，不是完整Accepted|
|严格Harbor no-network能力探测|1，unsupported|未降级接受门槛；当前Harborpublic不能冒充严格隔离|

Dispatcher终态冻结6个实现：Oracle、Nop、反馈正确/违规、保留正确/违规。Docker与Harbor均正常评分，正确全部1、错误全部0，backend_consistency=consistent、evidence_sufficient=true、panel_validated=true。它只验证人工Print42场景的核心机制。原始路径和hash见 [results-summary.json](validation/results-summary.json)。

命令、环境opt-in、退出码与wall time见 [commands.json](validation/commands.json)，完整默认回归见 [offline-unittest.log](validation/offline-unittest.log)。各检查stdout/stderr在validation目录，实际完整容器证据留在本worktree忽略的runs目录；未将大量实验数据再次提交进核心分支。

复现命令在README。核心代码仍有明确限制：没有自动Planner/Solver；没有新增真实模型端到端验收；Reviewer可能错；有限proof不能授权一般CSV修复；严格Harbor无网络不受本机支持。测试通过不取消这些边界。
