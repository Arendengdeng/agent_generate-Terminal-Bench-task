# Frozen end-to-end reliability experiment

Run from the repository root:

```bash
python3 experiments/01_e2e_reliability/run.py
python3 -m unittest discover -s tests -v
```

The driver reads the existing environment (falling back to known assignments in
`.env`, without executing it). `protocol.json` freezes the model and shared limits.
Each invocation creates a new run; `--run-id NAME` selects a unique explicit ID.
The driver never resumes a paused batch or increases its budget. A nonzero exit
means either `failed` or `incomplete`; inspect `experiment-result.json`.

Inputs live in `specs/jsonl-latest-record/`, and attributed Contract controls live
in `benchmarks/jsonl-latest-record/`. They are snapshotted into the run. The source
archive includes the framework and experiment files, not `.env`, caches or history.
The existing framework remains the canonical implementation of generation,
challenge, repair, validation and Controller decisions.

`native_controller_decision` retains the original decision enum, or null if the
Controller did not run. `experiment_result` is a separate passed/failed/incomplete
assessment. Original native evidence is never rewritten by experiment analysis.
Per-candidate decisions remain available in the original verification directories.

After native accept and independent validation, three frozen replays use new
containers and directories on the same host. Model generation and repair are
disabled. Test-level evidence includes collection, setup/call/teardown, outcomes,
skip/xfail, exceptions, assertion traceback sites, exit codes and rewards. Comparing
canonical reports ignores timing, stdout and environment-specific exception text;
it retains exception types and test assertion sites. Both backend and round
consistency are required. Empty reports, missing tests and equal execution errors
cannot count as successful rejection. Searched invalids receive supplemental
Docker baseline scoring because the native final Docker panel omits those controls;
this evidence is kept separate from native Controller evidence.

Each API transport attempt, including retries, uses the shared accounting layer.
Before an attempt, known total tokens plus unknown reserves plus the next reserve
must fit 500,000. The reserve is serialized message/tool bytes + 4,096 + maximum
completion tokens. Missing or invalid usage (including a timeout) retains its
reserve. It is an accounting estimate, not verified provider billing; usage
completeness and reconciliation differences are reported explicitly. No money
estimate is invented. The current framework does not expose the response model
identifier; the configured model is frozen, while that identifier remains unknown.

Preflight checks Docker, both local images, pinned Harbor and API reachability.
Harbor uses **public network mode**. Environment failures stop before generation;
reports do not claim accept, repair coverage, or three replays in that case. Restore
the required environment and invoke a new run rather than replacing old evidence.
Reports are placed in `reports/`; raw logs remain under ignored `runs/`. Accepted
exports are created only after all experiment checks pass.
