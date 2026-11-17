# attempts-20261117T012228Z-3d5a09dc-02

Experiment result: **incomplete**
Native Controller decision: `error`
Reason: `shared_budget_exhausted`
Evidence: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-02`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 40; known tokens: 312425; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 10 | 0 | 38443 | 0 |
| challenge_search | 25 | 0 | 250923 | 0 |
| independent_test | 5 | 0 | 23059 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "challenge_samples": [{"id": "000", "status": "rejected", "violation_status": "confirmed", "reason": "Frozen suite already rejects this confirmed incorrect solution."}, {"id": "001", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "The fixture and assertions themselves are in scope and correct for R2's \"max version\" behavior (key \"s\": 10 beats 9, output [{key:\"s\",version:10,value:\"ten\"}]), the exit_code 0 assertion follows R1, and the \"unchanged\" assertion follows R4. However the witness is mis-tagged/mis-derived: R2 explicitly requires ordering-independence AND tie-breaking \"last occurrence of the maximum version.\" This witness exercises neither — versions are distinct and the input is already ordered. So no assertion in the witness actually derives from the cited sentence's distinctive clauses (out-of-order input, last-max occurrence). The witness as scoped tests only the trivial subset and does not demonstrate R2 as quoted. Additionally, the witness omits any single-key trailing-newline edge but that is not required. Because the claimed assertions do not specifically follow from the cited Requirement's full statement (tie-break and ordering clauses unexercised), it cannot be confirmed as an R2 witness. The assertions are not wrong, but the witness does not faithfully represent the requirement it quotes; recommend adding a duplicate-max-version case (e.g., version 10 appearing twice with different values, expecting the later one) and/or shuffled input."}, {"id": "002", "status": "error", "violation_status": "unconfirmed", "reason": "shared model budget exhausted"}]}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
No framework changes or Git commit are made by this driver.

## Candidate failures

- Candidate 1: budget_exhausted; shared_budget_exhausted; stage=challenge.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-02/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Run command: `python3 experiments/01_e2e_reliability/run.py --run-id attempts-20261117T012228Z-3d5a09dc-02`

---

# attempts-20261117T012228Z-3d5a09dc-03

Experiment result: **incomplete**
Native Controller decision: `error`
Reason: `infrastructure_failure`
Evidence: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-03`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 36; known tokens: 317346; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 27 | 0 | 243301 | 0 |
| independent_test | 9 | 1 | 74045 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 0.
Repair activity: `[{"candidate": "0002", "test_repairs": 0, "challenge_repairs": 0, "challenge_samples": []}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
No framework changes or Git commit are made by this driver.

## Candidate failures

- Candidate 1: self_check_failure; 3 consecutive self-check failures: requires initial failure and all repaired requirements passing; stage=self_check.
- Candidate 2: infrastructure_failure; {"message": "Test Agent failed; see test-agent/tests.json and trace.jsonl", "type": "SynthesisError"}; stage=test_generation.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-03/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Run command: `python3 experiments/01_e2e_reliability/run.py --run-id attempts-20261117T012228Z-3d5a09dc-03`

---

# attempts-20261117T012228Z-3d5a09dc-04

Experiment result: **passed**
Native Controller decision: `accept`
Reason: `three_round_semantic_consistency`
Evidence: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-04`

Environment: same host, fresh containers; Harbor network mode: public.
Model: deepseek-flash; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.
API attempts: 33; known tokens: 207193; unknown attempts: 0; reserved unknown tokens: 0.

## Stage costs

| Stage | API attempts | Failures | Known tokens | Unknown usage |
|---|---:|---:|---:|---:|
| synthesis | 10 | 0 | 48624 | 0 |
| challenge_search | 18 | 0 | 131346 | 0 |
| independent_test | 5 | 0 | 27223 | 0 |

## Outcome and limitations

Original native reports remain unchanged; each replay has a separate decision and pytest evidence.
Completed revalidation rounds: 3.
Repair activity: `[{"candidate": "0001", "test_repairs": 0, "challenge_repairs": 0, "challenge_samples": [{"id": "000", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "The exit_code=0 and unchanged-input assertions are fine, but the `file` assertion on snapshot-latest.json compares raw text to a value ending in a newline and to a specific whitespace/format. The Contract explicitly states \"JSON 空白与转义形式不作要求\" (whitespace and escape form of the JSON are unconstrained), so requiring byte-exact text \"[{\\\"key\\\": \\\"db.url\\\", \\\"version\\\": 3, \\\"value\\\": \\\"postgres://b\\\"}]\\n\" imposes a formatting constraint not in the Contract — a correct implementation that emits compact JSON without trailing newline would fail. This assertion should use the `parsed_file` source with parser json (path [\"snapshot-latest.json\",\"json\"]) and the parsed value, per the required observation semantics. As written the assertion does not follow strictly from the cited Requirement plus Contract, so it is over-specified."}, {"id": "001", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "Fixture makes the tie-break assertion non-discriminating. In the witness, both version-5 records for key \"k\" have value \"same\", so \"keep the last occurrence among equal max versions\" is indistinguishable from keeping an earlier one. A wrong implementation that keeps the first occurrence of the maximum version would produce the identical output [{\"key\":\"k\",\"version\":5,\"value\":\"same\"}] and still pass. To test the last-occurrence rule of R2, the tied max-version records must have distinct values (e.g., version 5 \"first\" and version 5 \"last\") with the expected output being the later value; the out-of-order lower version is fine but does not by itself exercise the tie-break. The other assertions (exit_code 0, unchanged input) are valid and in scope, but the core behavioral claim for R2's tie-break is not derived conclusively from the fixture. Note the tie-break IS in the Contract (\"同一最大版本选择最后出现的记录\"), so it is legible; the issue is only that the supplied fixture fails to demonstrate it."}, {"id": "002", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "The expected value for the parsed_file assertion places \"e\\u0301\" (key \"e\" + combining acute, written as \"é\" in the JSON) first and \"é\" (U+00E9) last, and to make this consistent the fixture's second key is deliberately the decomposed form. That ordering is only correct if \"e\\u0301\" sorts before U+00E9, which is not derivable from the Contract: the input_spec requires each line to contain exactly the fields key/version/value as a NON-EMPTY STRING key, and Python string ordering on \"e\\u0301\" vs \"\\u00e9\" is well-defined but the Contract's \"按 key 的 Python 字符串升序排列\" applies to whatever key strings are present. The problem is that the expected array's key text is ambiguous as written in the assertion: one entry has key \"é\" that could be U+00E9 or decomposed, so I cannot confirm the assertion encodes exactly the two distinct keys from the fixture with the correct sort order. Additionally, the Contract's ordering is pure code-point ordering; the assertion's arrangement requires that the decomposed form (\"e\\u0301\", code points 0x65,0x301) sorts before U+00E9 (0xE9) — that happens to be true as raw string comparison, but since both keys are visually rendered as \"é\" the assertion text is not verifiably distinguishable, making the expected value ambiguous rather than a direct derivation. The exit_code and unchanged assertions are fine, but the sorted, distinct-key assertion cannot be confirmed as stated."}, {"id": "003", "status": "unconfirmed", "violation_status": "unconfirmed", "reason": "No definite violation, or witness rejected a correct control."}]}]`

No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.
Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.
If preflight is blocked, generation and revalidation are not run and model cost is zero.
No framework changes or Git commit are made by this driver.

## Candidate failures

- Candidate 1: None; None; stage=None.

## Environment evidence

Docker: `available`; Harbor: `available`; API: `available`.
Details: `runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-04/preflight/environment.json`.

## Reproduction

`python3 experiments/01_e2e_reliability/run.py` creates a new run with the same protocol.
Do not resume or overwrite this run after an environmental change; use a new run ID.
Run command: `python3 experiments/01_e2e_reliability/run.py --run-id attempts-20261117T012228Z-3d5a09dc-04`
