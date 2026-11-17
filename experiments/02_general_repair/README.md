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
