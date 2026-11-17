# 架构结论—源码—执行—Git 证据索引

基准HEAD c8be56d加初始dirty工作区，精确文件hash见 [initial-workspace.json](../runs/archive/audits/workspace-architecture-20261116/initial-workspace.json)，所有类/函数行号见 [source-symbols.json](../runs/archive/audits/workspace-architecture-20261116/source-symbols.json)。下列相对路径指原仓库；Git归属仅指机制引入，不能代替run内source snapshot。缺少精确运行版本绑定时以Unverified处理。

|ID|主要结论|实际源码/入口|运行/测试证据|历史或状态|
|---|---|---|---|---|
|A01|不是自动Planner，外部提供Plan/Contract|synthesis_agent/__main__.py::main，inputs.validate_inputs|examples/*/plan.json；CLI --help|0c2aa6d至当前；Planner Missing|
|A02|限制stdlib Linux Python CLI范围|inputs.validate_inputs，Config|tests/test_inputs_files.py|Implemented/Tested|
|A03|Contract完整追加到说明但不能保证正文一致|inputs.instruction_appendix，agent._run.dispatch|tests/test_agent.py；CSV drift fixture|当前新增有限gate，不是通用证明|
|A04|Synthesis是LLM局部工具循环|agent.SynthesisAgent._run，TOOLS/SYSTEM_PROMPT|runs/archive/candidates/acceptance-csv-01/trace.jsonl|0c2aa6d|
|A05|shell修改不持久，write_file才保存|agent.snapshot/dispatch，DockerSandbox.shell|tests/test_agent.py、test_docker_integration.py|Implemented/Tested|
|A06|self-check初始fail/修复全pass且绑定digest|agent._run.self_check/finish|历史candidate/self_check.json；三族model-acceptance|仅生成验收|
|A07|文件白名单/普通文件/容量约束|files.relative_path/FileSet/read_regular|tests/test_inputs_files.py|不是任意恶意代码安全证明|
|A08|独立Test看不到reference/probe|CandidateTask.test_input，agent.validate_test_input|tests/test_independent_verification.py；step3 frozen/test-input.json|68f1911|
|A09|Test生成仅collect成功与mapping结束|TestAgent._run.finish，TestSandbox.collect|step3_test_1112/rounds/*/generation/collection.json|不能证明测试正确|
|A10|映射只结构覆盖|common.validate_coverage|20轮各tests.json映射齐全但metrics有缺陷|Implemented有限|
|A11|真正执行只交付Contract产物|DockerTestRunner._trial，artifact_snapshot|test_test_agent_feedback_repair.DockerRepairTests；per-trial manifests|12936da|
|A12|error/null不可算正常拒绝|wrapper.classify，panel.outcome，harbor.parse_result|013144 execution/invalid_utf8_output/pytest.json|Implemented/Tested|
|A13|Controller纯规则、不执行repair|controller.decide/_decide|tests/test_controller.py；原始decision.json|dd3e178|
|A14|Test-only修复有界、每次全对照|test_repair_workflow.repair_tests|11-14 acceptance attempts/changes.patch/test-loop.json|12936da；当前已收紧授权|
|A15|Oracle-only异常不能授权改tests|model_feedback，TestAgent diagnose dispatch|11-14 initial/oracle_error失败与oracle-attribution-recheck|analysis_only宿主门禁|
|A16|Dispatcher真正调度、版本化、共享预算|repair.RepairRequest/RepairDispatcher.run|dispatcher-evidence-controls/acceptance.json；RealDispatcherTests|b5f01af；模型scripted|
|A17|普通归因是窄Contract/AST proof|attribution.verify_test_diagnosis/patch，json_attribution|tests/test_repair_dispatcher.py/test_json_attribution.py|非通用CSV自动修复|
|A18|外部critical issue不能强制授权|RepairDispatcher.run external_attribution_unverified|test_external_attribution_does_not_authorize_edits|Controller建议与授权区分|
|A19|测试scope与Synthesis scope独立|repair.SCOPES/_check_scope，SynthesisAgent.repair|scope/Contract/Plan immutability测试|当前已集成有限路径|
|A20|Challenge可读冻结tests，只写solution|challenge.ChallengeAgent.search/PROMPT|test_challenge_agent.py；live07 discovery/search/trace.jsonl|4d67040/c8be56d|
|A21|Reviewer fresh messages只审Contract/witness|challenge.review_witness/REVIEW_PROMPT|live07 candidates/008/review.json|共享模型；不是人工/形式证明|
|A22|违规确认和评分漏洞分开|run_challenge.evaluate，decide_challenge|live07 witness0 vs scoring1/1；历史候选rejected|raw重分类见下方|
|A23|audit重算wrapper与artifact_policy|challenge.audit_trial|challenge-fix-20261115-01/recorded-trial-audits.json|修复旧expected.json摘要遗漏|
|A24|Challenge补测只增补+独立补丁review|challenge_workflow.run_challenge/review_patch|live07 repair/repair/001/changes.patch与patch-review.json|局部Docker收敛|
|A25|当前普通all与--repair互斥支路|pipeline.verify最前分支及challenge_enabled|tests/test_repair_dispatcher.py/public entry|不能拼接统一已运行Pipeline|
|A26|最终holdout不回流模型|pipeline.verify holdout_started，model_feedback/evidence_packet拒绝|test_independent_panel.py；tests防泄漏|a98d994|
|A27|反馈/保留各正反已审查样本才充分|panel.prepare_panel/summarize，controller._decide|independent-controls05各run_result/validation-inputs|有限面板，不是一般正确性|
|A28|双后端tests/wrapper/policy/产物比对|panel.session/summarize，pipeline final|independent-controls05 final docker/harbor sessions|Integrated/Tested|
|A29|Harbor版本与separate verifier身份强校验|harbor.Harbor/parse_result，export_task|历史jobs/*/result.json/verifier/execution.json|固定0.25.0/schema1.3|
|A30|Harbor当前public、Docker原生none|exporter.HARBOR_NETWORK_MODE/task.toml，DockerSandbox.create_args|docs/history/step3-status.md；preflight/task.toml|非严格Harbor隔离|
|A31|WSL2缺NFT_FIB_INET阻断no-network|pipeline.preflight与历史provider probe|archive/verification/step3-harbor-*/exception/logs|不能记task assertion失败|
|A32|trace脱敏且长字段截断|trace.redact/summarize|trace.jsonl preview/redacted_sha256|不能完整恢复未截断消息|
|A33|当前API每次尝试有阶段/异常/usage|client.complete/exception_details/complete_accounted|client-reliability-20261115-01；tests/test_client_reliability.py|初始dirty修改|
|A34|未知usage不等于0，token上限可选|complete_accounted预算函数|Lightweight02 unknown attempt6；03 usage_complete true|无货币费用采集|
|A35|有限Instruction一致性gate|consistency.check_instruction；candidate/agent/attribution调用|csv-drift-regression-20261115-01/report.md|初始dirty新文件|
|A36|定向诊断限制工具/上下文/输出|diagnosis.evidence_packet，TestAgent.analyze/_run|csv drift diagnosis-input/fixtures；Lightweight03 1call|初始dirty；真实推理普遍质量Unverified|
|A37|三题型确有真实生成+smoke|tests/test_model_acceptance.py，PROBES|model-acceptance-a850ec92f14c421a9d5d790f3a3e7317/acceptance.json|与README“待办”冲突，按记录限域|
|A38|20轮全生成但测试质量差|V1 frozen source/PROMPT，evaluate/static_review|step3_test_1112/metrics.json/findings/各trial|20/1020；不混合后续版本|
|A39|14node仍5漏检2error|固定suite，wrapper分类|score-013144-final-analysis-20261115/最终分析报告.md与原execution|完整P0未成功|
|A40|live07真实漏洞存在但终验未完整|challenge_workflow+acceptance adapter|csv-e2e-live07 discovery/repair/terminal-freeze；无最终acceptance|本次snapshot Unverified终验|
|A41|Reviewer语义会误判|REVIEW_PROMPT与真实意见|live07 005/006/008 review.json|raw CSV过严/扩展名误解|
|A42|robustness两类受限变换不是语义补测|robustness.transform/prepare/verify|live03..07 preparation；test_e2e_acceptance.py|只集成专用adapter|
|A43|adapter passed不等于原生accept|acceptance.check_matrix/run_acceptance|terminal控制矩阵与native decision并列|历史panel残余miss允许|
|A44|另分支batch入口在master缺失|git show a050158:candidate_batch/runner.py/__main__.py|batch04/05 summary+model-calls|master仅specs/controls；不自动合并|
|A45|Lightweight03具体停止点|冻结driver+verify/test-loop/analyze|lightweight-pipeline-20261115-03/summary.json|17call，未Challenge/终验|
|A46|退役validation真实源码可恢复|git show stash@{0}^3:independent_verification/validation/*|archive/experiments/m0-m1-*；旧audit|本次只读；当前Missing集成|
|A47|实现库84/336核验是独立评估支路|implementation_library/{library,recipes,witnesses,scoring,harbor_batch}|evaluation_library/v2.1/library.json、RESULTS.json、archives|不当成生成成功率；核心排除|
|A48|原工作区不被覆盖，dirty核心完整复制|extract_core.py allowlist/hash|core-copy-manifest.json + git worktree list|新分支从c8be56d；仅新tip删文件|

## 本次直接核验原始证据

[008 raw-phase重分类](../runs/archive/audits/workspace-architecture-20261116/live07-008-raw-reclassification.json) 重算独立witness与两次14-node评分：违规witness0、Oracle1、known1，scoring1/1，和保存结果一致。进一步以当前audit_trial对冻结tests、实现、Verifier、artifact-policy、转交产物和phase进行完整只读重算，5项审计通过、Controller重算仍为repair：[完整重审](../runs/archive/audits/workspace-architecture-20261116/live07-008-full-audit.json)。它验证执行报告自洽，不替代Contract推导；008 raw-file assertion过严仍在主报告保留为Reviewer局限。

本次另外对20轮1020份原始execution.json，以各轮冻结nodeids调用当前classify重算，status/reward不一致为0：[原始重分类结果](../runs/archive/audits/workspace-architecture-20261116/baseline-raw-reclassification.json)。这是执行分类一致性，标签/自然语言缺陷仍依赖原独立见证与审查。20轮指标读取原metrics，与逐轮报告抽查/fixture/评分源交叉；013144主统计来自原trial及最终hash核验报告，不把历史Controller bool作为依据。大量run内旧绝对路径无法直接原地重放，索引按本仓库实际位置定位，未改原记录。

## 历史文档冲突的处理

- 11-14架构审计说无Challenge/Repair：是当时版本事实，当前由12936da/b5f01af/4d67040之后源码取代。
- README说token未采集：早期真实，当前client已记录已知usage与未知标志。
- docs/challenge-agent列json_file：当前validate_witness不支持，按源码；parsed_file才是当前结构化文件算子。
- docs说Challenge完整真实闭环未验收：live07已有真实发现+局部Docker补测，但缺完整终验，更新局部进展、不升级最终Accepted。
- README三题型待办：实际model-acceptance记录已有generation+smoke，仍没有三题型完整独立终验。

## 文件级与源码索引

- [完整实验清单](experiment-inventory.md)
- [全部artifact路径/大小/hash](../runs/archive/audits/workspace-architecture-20261116/artifact-index.tsv)
- [子运行结构化结果](../runs/archive/audits/workspace-architecture-20261116/experiment-records.json)
- [函数/类行号](../runs/archive/audits/workspace-architecture-20261116/source-symbols.json)
- [初始dirty diff](../runs/archive/audits/workspace-architecture-20261116/initial-tracked-changes.patch)
- [提炼复制hash清单](../runs/archive/audits/workspace-architecture-20261116/core-copy-manifest.json)
- [原工作区离线回归](../runs/archive/audits/workspace-architecture-20261116/original-unittest.log)

## 本次提炼结果补充

[A49 验证命令](../runs/archive/audits/workspace-architecture-20261116/core-validation/commands.json)、[A50 当前真实Dispatcher/六对照结果](../runs/archive/audits/workspace-architecture-20261116/core-validation/results-summary.json)、[A51 原工作区完整性](../runs/archive/audits/workspace-architecture-20261116/original-workspace-integrity.json)、[A52 branch/commit](../runs/archive/audits/workspace-architecture-20261116/core-branch.json)。当前真实容器机制通过不代表付费真实模型已验收；严格Harbor无网络unsupported另列。
