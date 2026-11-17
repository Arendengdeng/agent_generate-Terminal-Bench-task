# 运行记录索引

2026-11-14 按用途归档现有运行记录。没有删除任务、日志、报告或失败证据。新运行输出到 `runs/<experiment>/<run_id>/`；已有历史目录保持原位。

原始证据内容保持不变；其中内嵌的历史绝对路径不会自动迁移。本次 Test Agent 反馈修复验收的路径与逐文件哈希见 [迁移索引](archive/verification/2026-11-14-test-agent-feedback-repair/relocation-index.json)。其他历史记录按下列分类目录定位；重新执行命令时使用归档后的路径。

候选生成成功、测试生成成功和 Oracle/Nop 基础通过是不同状态，不代表任务质量已获得完整证明。

## candidates

Synthesis 生成候选；candidate_generated 仅表示参考解法自检通过。

- [acceptance-csv-01](archive/candidates/acceptance-csv-01)
- [acceptance-csv-02](archive/candidates/acceptance-csv-02)
- [acceptance-csv-03](archive/candidates/acceptance-csv-03)

## verification

独立测试生成、导出、Harbor 验收及测试修复集成记录；各目录状态独立。

- [2026-11-14：Test Agent 真实执行反馈与有限修复验收](archive/verification/2026-11-14-test-agent-feedback-repair/README.md)：首次验收、Oracle 归因修正复验、最终 Harbor 复验。

- [step3-acceptance-20261112.json](archive/verification/step3-acceptance-20261112.json)
- [step3-acceptance-public-20261112.json](archive/verification/step3-acceptance-public-20261112.json)
- [step3-harbor-160dbbb7893146d6846cbf7c74945cf9](archive/verification/step3-harbor-160dbbb7893146d6846cbf7c74945cf9)
- [step3-harbor-740bf1dbf61c46559037eed4c06a6ccf](archive/verification/step3-harbor-740bf1dbf61c46559037eed4c06a6ccf)
- [step3-historical-inspection](archive/verification/step3-historical-inspection)
- [step3-live-01](archive/verification/step3-live-01)
- [step3-live-export-01](archive/verification/step3-live-export-01)
- [step3-public-01](archive/verification/step3-public-01)
- [test-repair-artifacts-612c75f40f154018ab78268040e9d83e](archive/verification/test-repair-artifacts-612c75f40f154018ab78268040e9d83e)
- [test-repair-binary-30333b52e9d94fe99febb6ace71c0961](archive/verification/test-repair-binary-30333b52e9d94fe99febb6ace71c0961)
- [test-repair-docker-bb8b88778ec5442bb51b7cd24f4ad2dc](archive/verification/test-repair-docker-bb8b88778ec5442bb51b7cd24f4ad2dc)
- [test-repair-harbor-6a0424623a744d3faa2021dacfed2e0c](archive/verification/test-repair-harbor-6a0424623a744d3faa2021dacfed2e0c)

## diagnostics

依赖或环境失败的诊断，不能视为任务验收通过。

- [docker-unavailable-check](archive/diagnostics/docker-unavailable-check)
- [model-acceptance-0ea5d9bb75be4dd18d7101f32d789b1c](archive/diagnostics/model-acceptance-0ea5d9bb75be4dd18d7101f32d789b1c)
- [step3-historical-preflight](archive/diagnostics/step3-historical-preflight)
- [step3-live-run-01](archive/diagnostics/step3-live-run-01)

## experiments

历史语义验证子系统的实验记录；该接口已退役。

- [m0-m1-acceptance-20261112](archive/experiments/m0-m1-acceptance-20261112)
- [m0-m1-cli-smoke-20261112](archive/experiments/m0-m1-cli-smoke-20261112)

## audits

测试质量审查及反例。

- [csv-overstrict-audit](archive/audits/csv-overstrict-audit)

## support

辅助镜像构建文件。

- [step3-image](archive/support/step3-image)

## 本次新增归档位置

- [架构审计原始证据](archive/audits/workspace-architecture-20261116/)：原 `reports/audit-artifacts/`，内部内容与历史路径保持原样。
- [Candidate Orchestrator 真实批次](01_e2e_reliability/candidate-orchestrator-live-20261116T173411Z/)：原 `reports/` 下同名目录；[维护报告](../reports/candidate-orchestrator-live-20261116T173411Z.md)。
- [工作区整理记录](../reports/workspace-cleanup.md)。

## 历史顶层归档

[实现库历史归档](archive/legacy/implementation-library-v2.1-20261115/) 由原 `archives/` 整体迁入；内部内容不变。迁移摘要和保留原因见 [根目录整理记录](../reports/root-directory-cleanup.md)。
