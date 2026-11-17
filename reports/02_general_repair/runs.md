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

---

# e2e-20261117T092546Z-91dc641b

Experiment result: **incomplete**
Native Controller decision: `needs_review`
Reason: `shared_budget_exhausted`
Evidence: `runs/02_general_repair/e2e-20261117T092546Z-91dc641b`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 40; known tokens: 266859; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 29 | 0 | 202503 | 0 |
| unattributed | 5 | 0 | 30257 | 0 |
| independent_test | 6 | 0 | 34099 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0002", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "model_call_budget_exceeded", "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: no_progress; 8 consecutive tool calls without persisted file changes; stage=generation.
- Candidate 2: budget_exhausted; shared_budget_exhausted; stage=repair.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/e2e-20261117T092546Z-91dc641b/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_protocol.json --run-id e2e-20261117T092546Z-91dc641b`. Use a new unique run ID for another execution.

---

# explore80-20261117T170350Z-77905313

Experiment result: **incomplete**
Native Controller decision: `None`
Reason: `repeated_failure`
Evidence: `runs/02_general_repair/explore80-20261117T170350Z-77905313`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.
API attempts: 45; known tokens: 370599; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Tools | Failures | Input tokens | Output tokens | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthesis | 23 | 29 | 0 | 76315 | 12620 | 88935 | 0 |
| self_check_followup | 22 | 22 | 0 | 268691 | 12973 | 281664 | 0 |
| independent_test | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| acceptance_test | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnosis | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| synthesis_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_search | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_review | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| unattributed | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: probe_defect; 3 consecutive self-check failures: probe execution error (not a task assertion failure); stage=self_check.
- Candidate 2: self_check_failure; 3 consecutive self-check failures: requires initial failure and all repaired requirements passing; stage=self_check.
- Candidate 3: self_check_failure; 3 consecutive self-check failures: requires initial failure and all repaired requirements passing; stage=self_check.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/explore80-20261117T170350Z-77905313/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_exploration_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_exploration_protocol.json --run-id explore80-20261117T170350Z-77905313`
