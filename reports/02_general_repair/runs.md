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

---

# selfcheck-e2e-20261117-atomic-01

Experiment result: **incomplete**
Native Controller decision: `needs_review`
Reason: `shared_budget_exhausted`
Evidence: `runs/02_general_repair/selfcheck-e2e-20261117-atomic-01`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.
API attempts: 80; known tokens: 400211; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Tools | Failures | Input tokens | Output tokens | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthesis | 8 | 9 | 0 | 34488 | 3706 | 38194 | 0 |
| self_check_followup | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| independent_test | 5 | 7 | 0 | 24397 | 4135 | 28532 | 0 |
| acceptance_test | 5 | 7 | 0 | 23991 | 3932 | 27923 | 0 |
| diagnosis | 62 | 115 | 0 | 298263 | 7299 | 305562 | 0 |
| test_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| synthesis_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_search | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_review | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| unattributed | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "model_call_budget_exceeded", "general_attempts": [], "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: budget_exhausted; shared_budget_exhausted; stage=repair.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/selfcheck-e2e-20261117-atomic-01/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id selfcheck-e2e-20261117-atomic-01`

---

# selfcheck-e2e-20261117-atomic-02

Experiment result: **incomplete**
Native Controller decision: `needs_review`
Reason: `shared_budget_exhausted`
Evidence: `runs/02_general_repair/selfcheck-e2e-20261117-atomic-02`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.
API attempts: 80; known tokens: 553837; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Tools | Failures | Input tokens | Output tokens | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthesis | 18 | 19 | 0 | 101432 | 8812 | 110244 | 0 |
| self_check_followup | 9 | 11 | 0 | 141139 | 7722 | 148861 | 0 |
| independent_test | 10 | 15 | 0 | 50606 | 6894 | 57500 | 0 |
| acceptance_test | 10 | 14 | 0 | 45472 | 6062 | 51534 | 0 |
| diagnosis | 20 | 34 | 0 | 83395 | 1942 | 85337 | 0 |
| test_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| synthesis_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_search | 12 | 17 | 0 | 93968 | 4662 | 98630 | 0 |
| challenge_review | 1 | 1 | 0 | 1387 | 344 | 1731 | 0 |
| unattributed | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "final_validation_failed", "general_attempts": [], "challenge_samples": [{"id": "000", "status": "confirmed", "violation_status": "confirmed", "reason": null}]}, {"candidate": "0002", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "model_call_budget_exceeded", "general_attempts": [], "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: verification_failure; final_validation_failed; stage=challenge.
- Candidate 2: budget_exhausted; shared_budget_exhausted; stage=repair.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/selfcheck-e2e-20261117-atomic-02/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id selfcheck-e2e-20261117-atomic-02`

---

# selfcheck-e2e-trial3-20261117-01

Experiment result: **incomplete**
Native Controller decision: `error`
Reason: `infrastructure_failure`
Evidence: `runs/02_general_repair/selfcheck-e2e-trial3-20261117-01`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.
API attempts: 25; known tokens: 119264; unknown attempts: 3; reserved unknown tokens: 107819.

## Stage costs

| Stage | API attempts | Tools | Failures | Input tokens | Output tokens | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthesis | 10 | 10 | 0 | 42406 | 4264 | 46670 | 0 |
| self_check_followup | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| independent_test | 5 | 7 | 0 | 24746 | 5855 | 30601 | 0 |
| acceptance_test | 4 | 5 | 0 | 20581 | 4089 | 24670 | 0 |
| diagnosis | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| synthesis_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_search | 6 | 8 | 3 | 16749 | 574 | 17323 | 3 |
| challenge_review | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| unattributed | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "final_validation_failed", "general_attempts": [], "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: infrastructure_failure; {"message": "SynthesisError", "type": "CHALLENGE_INCOMPLETE"}; stage=challenge.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/selfcheck-e2e-trial3-20261117-01/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id selfcheck-e2e-trial3-20261117-01`

---

# selfcheck-e2e-trial3-20261117-02

Experiment result: **passed**
Native Controller decision: `accept`
Reason: `three_round_semantic_consistency`
Evidence: `runs/02_general_repair/selfcheck-e2e-trial3-20261117-02`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.
API attempts: 65; known tokens: 570363; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Tools | Failures | Input tokens | Output tokens | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| synthesis | 10 | 10 | 0 | 45164 | 5002 | 50166 | 0 |
| self_check_followup | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| independent_test | 5 | 7 | 0 | 23154 | 3267 | 26421 | 0 |
| acceptance_test | 5 | 7 | 0 | 23013 | 3177 | 26190 | 0 |
| diagnosis | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| synthesis_repair | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| challenge_search | 41 | 46 | 0 | 451810 | 9291 | 461101 | 0 |
| challenge_review | 4 | 4 | 0 | 5357 | 1128 | 6485 | 0 |
| unattributed | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 3.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "general_repairs": 0, "general_stop_reason": "full_validation_passed", "general_attempts": [], "challenge_samples": [{"id": "000", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "The witness is in scope for R1 (argv with $WORK input/output paths matches the Contract command form; fixture lines are valid JSONL per input_spec). However, the assertions do not all follow directly. The exit_code=0 assertion is fine. The `file` assertion on out.json compares raw text to an exact string `[{\"key\": \"cache.ttl\", ...}, {\"key\": \"db.host\", ...}]\\n`, but the Contract explicitly states \"JSON 空白与转义形式不作要求\" (whitespace and escaping form are not constrained). A correct implementation may emit different but valid JSON whitespace (e.g., no trailing newline, different separators, indentation), so the raw-text equality assertion is unnecessarily strict and can fail a correct implementation. The output should instead be verified via the `json` source with the parsed array value, which is the format-matching operator for a JSON array. The `unchanged` assertion on in.jsonl is consistent with R4 but is not derived from the cited R1 quote. Because the raw-text file assertion imposes formatting constraints the Contract explicitly disclaims, and the observation operator does not robustly parse the specified JSON format, the witness is not confirmed."}, {"id": "001", "status": "rejected", "violation_status": "confirmed", "reason": "Frozen suite already rejects this confirmed incorrect solution."}, {"id": "002", "status": "rejected", "violation_status": "confirmed", "reason": "Frozen suite already rejects this confirmed incorrect solution."}, {"id": "003", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "The witness targets R4 but its fixtures/argv use whitespace outside the JSON objects on each input line (\"   \", \"\\t\", trailing spaces). The input_spec describes \"UTF-8 JSONL；每行恰含 key、version、value\" and permits no other illegal input, but it does not explicitly say whether trailing whitespace after the JSON object is allowed. The out.json assertion (a=version 1, b=version 2, last/tie rules, key sort order) is derivable from R2/R3 and the Contract, and the unchanged(input.jsonl) and exit_code=0 assertions follow from R4/R1 — those are fine. The risk is that the fixture text includes trailing/inter-line whitespace whose acceptance is not unambiguously guaranteed by the Contract; a correct implementation that strictly rejects or mishandles lines with trailing whitespace beyond what \"恰含\" strictly allows could legitimately fail this witness. The contract quotes do not authorize such fixture formatting, so the witness relies on behavior not strictly derivable from the Contract. Reject as ambiguous: use fixtures with exactly the specified JSONL format (no extra whitespace) for an R4 input-immutability check."}]}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
Git commit is not created; the frozen source archive includes any pre-run framework changes.

## Candidate failures

- Candidate 1: None; None; stage=None.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/02_general_repair/selfcheck-e2e-trial3-20261117-02/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Original run command: `python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id selfcheck-e2e-trial3-20261117-02`
