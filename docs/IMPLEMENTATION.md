# 实现说明

输入为调用方提供的Plan/Contract，范围为Linux Docker内Python标准库CLI修复。自动Planner未实现。

|阶段|实际模块/入口|
|---|---|
|输入与规范|synthesis_agent.inputs、consistency；可选format_rules显式配置|
|生成|SynthesisAgent；FileSet、DockerSandbox、Probe/self_check；python -m synthesis_agent|
|独立测试|TestAgent独立messages、pytest collect、执行反馈、有限修复|
|评分|CandidateTask/Static Checker、DockerTestRunner、Verifier wrapper|
|修复|Controller、RepairRequest、RepairDispatcher、版本/预算与宿主repair_proofs|
|主动反例|ChallengeAgent、Witness Reviewer、Patch Reviewer、两次冻结评分确认误通过、只增补测试|
|终验|panel、pipeline.verify、Harbor exporter/runner；反馈/holdout各正反对照；双后端冻结比较|
|批次|CandidateOrchestrator → Synthesis → 原生verify；abandoned、暂停、resume、共享预算|
|模型客户端|OpenAI兼容工具协议、错误链诊断、有限传输重试、usage与未知用量保留|

离线运行：按README安装后执行`python scripts/check_core.py`及`python -m unittest discover -s tests -v`。
无模型冻结示例：`python scripts/run_frozen_example.py --output runs/new-export`。
付费完整E2E命令、环境变量和批次选项见README；本次未运行任何付费模型。

所有输出使用新目录。candidate_generated/tests_generated不是Accepted；编排器仅消费原生accept与independent_validation双条件。
已确认Challenge错误实现现在进入最终Docker及Harbor，不能用局部回归代替终验。

普通all的Test Loop/Challenge与跨模块Dispatcher仍是不同路径；显式Challenge与repair互斥。
普通自动proof仅支持有限stdout/JSON模板，不支持通用CSV/JSONL/manifest语义修复。
格式规则默认不启用CSV专门逻辑；Contract附录一致性一直检查；no_findings不是语义证明。
Harbor当前public网络，原生Docker为none，不能据此宣称严格Harbor无网络验收。
Reviewer可能误判，有限对照与有限搜索不证明一般正确性。证据仍有绝对路径，迁移旧run可能需重新执行。

与总设计相比缺自动Planner/Contract起草、普通Solver、难度校准、跨任务多样性去重和正式数据集发布；
通用根因归因、统一多类修复循环、可移植证据与三轮稳定性复验也未完成。

另一分支candidate-batch-expansion的六规范runner、独立克隆Probe归因/repair_probe/checkpoint、
stash中的validation子系统及implementation_library研究评估没有纳入或冒充主线功能。
