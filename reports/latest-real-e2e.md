# 最近真实E2E证据（历史实验，本次不重跑）

原始证据目录：`/home/zyl/projects/agent_generate Terminal Bench task/reports/candidate-orchestrator-live-20261116T173411Z`。摘要及关键原始文件SHA256见[latest-real-e2e-summary.json](latest-real-e2e-summary.json)。
未复制大型batch、trace、Harbor trials或模型配置；原始证据仍留源项目。

模型deepseek-flash；原CSV Plan/Contract。共生成2个新候选：1号self_check_failure后abandoned；2号最终Accepted。
累计54次模型调用、428694 tokens、67次工具；初始Test门禁无需修复，Challenge发现R2缺口后增补1轮。
原始在线accept存在终验Harbor遗漏，原始离线复审为error，均保留。修复生产终验后对同一冻结候选/测试在新目录
frozen-final-verification重新执行，新增模型调用0；原生decision=accept、independent_validation=true；
frozen-final-native-review再次accept。不能将原有遗漏在线结果直接当作最终成功。

两个后端各7个对象正常评分：Oracle、反馈正确、holdout正确=1；Nop、反馈错误、holdout错误、Challenge错误实现=0。
成功候选在batch/candidates/0002/candidate；完整真实Challenge在batch/candidates/0002/verification/challenge；
最终任务包在frozen-final-verification/export/task；预算核对usage-audit.json，历史完整性见final-original-evidence-integrity.json。

这是一例经历运行期间修复及冻结补跑的成功，不是预先冻结代码后一次无干预成功，也未完成三轮稳定性复验。
Resume在该真实批次未触发；本次仅离线测试验证。JSONL/manifest没有由该CSV案例自动获得Accepted证据。
其他分支Probe改进见源项目real-model-e2e-worktree/reports/synthesis-probe-reliability-audit.md，未合入本次核心。
