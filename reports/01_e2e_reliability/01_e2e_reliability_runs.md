# 20261117T010722Z-72d855b3

Experiment result: **incomplete**
Native Controller decision: `error`
Reason: `source_changed_during_experiment`
Evidence: `runs/01_e2e_reliability/20261117T010722Z-72d855b3`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 16; known tokens: 83777; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 11 | 0 | 56210 | 0 |
| independent_test | 5 | 0 | 27567 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
No framework changes or Git commit are made by this driver.

## Candidate failures

- Candidate 1: None; {"message": "execution_error", "type": "TEST_LOOP_ERROR"}; stage=test_execution.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/01_e2e_reliability/20261117T010722Z-72d855b3/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Run command: `python3 experiments/01_e2e_reliability/run.py --run-id 20261117T010722Z-72d855b3`
