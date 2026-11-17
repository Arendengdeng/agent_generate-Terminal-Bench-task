# 02_general_repair

Test whether Contract plus execution evidence supports reusable diagnosis and repair. Shared implementation remains in the existing source packages; this directory defines the experiment only.

Develop on CSV, then freeze source/configuration/prompts and evaluate JSONL, manifest and the CLI argument example. Each frozen case supplies `id`, `task_type`, `candidate`, `tests`, `acceptance_tests`, `controls_manifest`. Use separately reviewed feedback and held-out controls of both classes. A case directory or model-provided classification is not an independent review.

```bash
python3 -m independent_verification --experiment general-repair \
  --comparison-cases /absolute/path/to/frozen-cases.json \
  --output runs/02_general_repair/UNIQUE_RUN_ID --repetitions 3 \
  --harbor-python /absolute/path/to/harbor-venv/bin/python
```

The existing entry point executes both policies on identical frozen inputs and shared budget limits. It stops on changed input/source hashes and preserves each progress record. See `protocol.json` for the fixed comparison rules. Protocol tests use injected runners and cannot count as native acceptance.

Run framework checks with `python3 -m unittest discover -s tests -v`. The real fault-injection smoke is opt-in:

```bash
GENERAL_REPAIR_DOCKER=1 HARBOR_PYTHON=/absolute/path/to/harbor-venv/bin/python \
  python3 -m unittest tests.test_general_repair_integration -v
```

Set `GENERAL_REPAIR_LIVE=1` as well, with the usual model configuration, to test live model diagnosis and patching. This smoke injects a known development-test defect into a handwritten arithmetic task outside existing proof adapters; it does not establish cross-task repair performance. Output goes to a unique `runs/02_general_repair/<run_id>/`. Reports belong in `reports/02_general_repair/` and identify the run IDs.

The smoke defaults to 16 shared model calls and 40 tool calls. Override `GENERAL_REPAIR_MAX_MODEL_CALLS` and `GENERAL_REPAIR_MAX_TOOL_CALLS` to test a separately recorded budget level; 40/120 matches framework defaults. Results from different budgets or source versions must not be pooled as one frozen comparison.

## Full Candidate Orchestrator integration

```bash
python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_protocol.json
```

This reuses the Step 1 driver and canonical orchestrator with the same 40 model / 120 tool /
500,000 token / 10 candidate limits, JSONL input snapshots and reviewed controls.
The generic dispatcher generates independent development and acceptance suites, freezes
acceptance before repair, diagnoses development execution errors and assertion failures,
and authorizes at most two shared component repairs. Its final validation now invokes
real Challenge search (up to four attempts), Docker and public-network Harbor. Final
Challenge has zero test edits because acceptance is frozen: a bypass is recorded and
rejects the candidate. This stricter freeze boundary is explicit in e2e_protocol.json;
development repairs retain the original limit. Three frozen replays run only after native
accept. The historical Step 1 protocol and old runs are unchanged. Reports and evidence
use experiment_id=02_general_repair. No subsystem smoke counts as full generation success.

## Exploratory run with higher shared limits

```bash
python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/e2e_exploration_protocol.json
```

This separately frozen exploratory protocol allows 80 model attempts, 240 Agent tool
calls and 1,000,000 reported/reserved tokens for the whole batch. There are no stage
reservations or quotas. Existing candidate, repair, Challenge, no-progress and acceptance
conditions remain unchanged. The generic Synthesis/Test prompts also clarify Contract
boundaries and evidence-based correction, so comparisons cannot isolate a budget effect.
No required generation or verification is skipped to reduce calls. Three frozen replays
remain conditional on native accept, with Harbor public networking explicitly recorded.

Trace phase metadata and experiment analysis distinguish initial synthesis, follow-up
after failed self-check, development/acceptance test generation, diagnosis, test/Synthesis
repairs, Challenge search and witness review. API retries are counted in shared totals.
Self-checks, Docker panels and host process durations are separate execution observations,
not additional Agent tool charges. Full input/output token counts and candidate/stage
breakdowns reconcile against the original ledger. Read-only calls are not automatically
classified as waste. Not-reached stages supply no estimate of their full cost. Historical
40-call runs are preserved and are not pooled with the exploratory run as a success rate.

## Self-check diagnosis and atomic repair regression

```bash
python3 experiments/02_general_repair/self_check_replay.py --run-id UNIQUE_SELF_CHECK_RUN_ID
python3 experiments/01_e2e_reliability/run.py --protocol experiments/02_general_repair/self_check_e2e_protocol.json --run-id UNIQUE_E2E_RUN_ID
SELF_CHECK_DOCKER=1 python3 -m unittest tests.test_synthesis_self_check -v
```

`benchmarks/jsonl-latest-record/self_check_cases.json` freezes the first Self-check
file states of candidates 0001/0002/0003 from `explore80-20261117T170350Z-77905313`.
Every file manifest and digest was checked against the original build logs. Candidate
0003 also supplies its second check's passing Solution checkpoint for rollback testing.
These are development regression cases, not a blind generalization panel.

The replay freezes inputs and source, runs each initial case three times with the new
mechanism and once with the Git HEAD baseline in isolated Python workers. The baseline
system prompt receives an existing-snapshot mode and the untrusted current file data
to avoid task regeneration. Improved replay also receives all current file data. Each invocation has the exploratory protocol's independent 80 model /
240 tool / 1,000,000 token limits, eight unchanged calls and three failing checks;
the improved initial check and automatic regressions count against these limits.
No retry-until-success or feedback from evaluation is allowed. The baseline has one
repetition and cannot establish a reliable comparative success rate.

Only Plan, Contract, candidate files and runtime observations enter the model's tools.
The evaluator and reviewed feedback controls run after the model has stopped; they
are never mapped into its containers or passed to its client. The evaluator checks
Contract behavior and the final Probe against correct/invalid controls, including a
deterministic 1000-record panel. It cannot prove all checks are sufficient or that a
proposed explanation is correct; review the stored hypotheses and actual diff as well.
No held-out controls are used for this development replay.

`comparison.json`, per-invocation `replay-result.json`, immutable progress files and
private Self-check version histories preserve failures, budget use, original failure
reproduction, and evaluation results. Missing/error evaluation is never successful
rejection. The separate full E2E protocol changes only the variant description; it
keeps independent testing, Repair, Challenge, acceptance and conditional frozen replay.
