

# 01_e2e_reliability: attempts-20261117T012228Z-3d5a09dc

experiment_id: `01_e2e_reliability`; campaign run_id: `attempts-20261117T012228Z-3d5a09dc`

最多 10 次新尝试，首次实验成功即停止；每次独立使用原协议预算。
成功要求原生验收与三轮冻结复验全部通过。未修改测试或框架以获得通过。

| 次数 | run_id | 原生判定 | 实验结果 | 模型调用 | 工具调用 | 已知 Token | 修复次数 | 原因 |
|---:|---|---|---|---:|---:|---:|---:|---|
| 1 | `attempts-20261117T012228Z-3d5a09dc-01` | 未完成 | incomplete | 33 | 41 | 335841 | 0 | external_runtime_restart |
| 2 | `attempts-20261117T012228Z-3d5a09dc-02` | error | incomplete | 40 | 44 | 312425 | 0 | shared_budget_exhausted |
| 3 | `attempts-20261117T012228Z-3d5a09dc-03` | error | incomplete | 36 | 37 | 317346 | 0 | infrastructure_failure |
| 4 | `attempts-20261117T012228Z-3d5a09dc-04` | accept | passed | 33 | 39 | 207193 | 0 | three_round_semantic_consistency |

Campaign status: `passed`; reason: `first_success`.

Totals: `{"model_calls": 142, "tool_calls": 161, "test_repairs": 0, "challenge_repairs": 0, "unknown_token_reserve": 0, "known_tokens": 1172805, "completed_attempts": 4, "native_accepts": 1, "experiment_successes": 1}`.

Machine-readable record: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc/campaign.json`.
