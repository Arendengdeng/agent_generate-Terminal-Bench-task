# e2e-20261117T061542Z-706acadd

experiment_id: `02_general_repair`

Experiment result: **incomplete**
Native Controller decision: `needs_review`
Reason: `{"message": "Test Agent context budget exceeded", "type": "BudgetExceeded"}`
Evidence: `runs/02_general_repair/e2e-20261117T061542Z-706acadd`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 24; known tokens: 132358; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 11 | 0 | 62036 | 0 |
| unattributed | 5 | 0 | 25644 | 0 |
| diagnosis | 3 | 0 | 12046 | 0 |
| independent_test | 5 | 0 | 32632 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "call_budget_exhausted", "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: budget_exhausted; {"message": "Test Agent context budget exceeded", "type": "BudgetExceeded"}; stage=repair.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/e2e-20261117T061542Z-706acadd/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_protocol.json --run-id e2e-20261117T061542Z-706acadd`. Use a new unique run ID for another execution.
