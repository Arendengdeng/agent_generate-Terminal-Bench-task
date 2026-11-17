# 最多三遍 E2E：第二遍完整成功

- experiment_id: `02_general_repair`
- run_ids: `selfcheck-e2e-trial3-20261117-01`, `selfcheck-e2e-trial3-20261117-02`
- 实际启动 2 遍；第二遍完整成功后停止，第 3 遍为 **not_run**。
- 代码版本: `af29dd1b37b6c44c5918015dc5edea56207e6f2ed53744c5608189018b67cb09`。
- Git 基线 `602ee8f`，沿用已有 staged/dirty 修改；本轮未修改实现、协议、模型配置、测试或验收规则，未创建 commit。
- 模型配置: `deepseek-flash`。每遍独立上限: 80 次模型调用、240 次工具调用、1,000,000 Token、10 个候选；沿用既有自检、Repair、Challenge 和原生验收条件。

## 两次新运行

| 遍数 / run_id 后缀 | 完整实验结果 | Native Controller | 模型 API 尝试 | Agent 工具调用 | 接口报告 Token | 停止原因 |
|---|---|---|---:|---:|---:|---|
| 01 | incomplete | error | 25 | 30 | 119,264 | 模型 API 临时 DNS 解析失败 |
| 02 | **passed** | **accept** | 65 | 74 | 570,363 | three_round_semantic_consistency |

第一遍已通过 Synthesis 自检、独立测试生成并进入 Challenge。三次 API 尝试记录 `URLError / gaierror / Temporary failure in name resolution`，包括两次传输重试；该运行按原机制停止为 infrastructure_failure，不算模型质量拒绝或验收成功。这三次尝试用量未知，另预留 107,819 Token，未将未知用量写成零。结束后只读预检确认 API 恢复，另存 `01/postrun-preflight/`，再以全新 run ID 启动第二遍，没有续写或覆盖失败运行。

第二遍未经人工干预获得原生 `accept`，`independent_validation=true`；同一冻结任务和测试的三轮复验全部通过，独立 Controller 重判均为 accept。原生评分矩阵含 16 项 Docker/Harbor 评分，无后端差异；每轮复验均与该矩阵一致。

| 冻结复验 | 结果 | 新增模型调用 | 新增 Agent 工具调用 |
|---|---|---:|---:|
| 1 | passed | 0 | 0 |
| 2 | passed | 0 | 0 |
| 3 | passed | 0 | 0 |

第二遍成功候选只有一次 Synthesis Self-check、零次 Self-check 修复，独立 Repair 也为零次；Challenge 搜索运行四次。本轮证明当前完整流程能够原生完成及重复验证，不能据此单独归因于修复机制改进，也不能把三轮冻结复验算作三次独立任务生成成功。

两遍源码和输入完整性均为 true；第二遍总用时 1546.424 秒，包含三轮容器复验。Docker 无网络，Harbor 为 **public** 网络，不能称为严格无网络验收。

## 证据和导出

- 两遍原生证据分别位于 `runs/02_general_repair/selfcheck-e2e-trial3-20261117-01/`、`runs/02_general_repair/selfcheck-e2e-trial3-20261117-02/`，以各自 `experiment-result.json`、`batch/batch.json`、`provenance/` 为准。
- 第二遍的 `revalidation-1-summary.json`、`revalidation-2-summary.json`、`revalidation-3-summary.json` 保存逐轮评分与重新判定；`three-trials-summary.json` 汇总本次“至多三遍”请求。
- accepted 导出: `artifacts/accepted/jsonl-latest-record-selfcheck-e2e-trial3-20261117-02/`，包含 task、provenance 与 `acceptance.json`；导出保持为生成产物，未暂存进普通 Git 提交。
- 本轮仅新增本报告，既有 `reports/02_general_repair/runs.md` 由实验驱动追加结果；历史失败记录和已暂存的实现保持不变。

复现使用同一协议和新的唯一 run ID:

```bash
python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id NEW_UNIQUE_RUN_ID
```
