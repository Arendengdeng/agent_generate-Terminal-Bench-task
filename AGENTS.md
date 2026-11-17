# Repository rules for all Coding CLIs

> This file is the single source of truth for repository organization and collaborative development. These rules apply to Claude Code, Gemini CLI, Codex, and other coding agents. Read `README.md` and `docs/REPO_STRUCTURE.md` when relevant before editing.

## 1. First inspect; do not reorganize by default

- Current first-version scope: Linux Docker, single-container Python-standard-library CLI/data-processing repair tasks. Do not silently transform an out-of-scope request into a different task; use the project's explicit unsupported outcome when applicable.

- Before making changes, inspect `git status --short`, the current branch/worktree, relevant directory structure, and existing entry points/tests.
- Prefer existing modules and directories. Never create a new directory, duplicate module, or second entry point merely for convenience.
- This repository may not yet match the target layout in `docs/REPO_STRUCTURE.md`. Do not perform a broad migration unless explicitly requested. Preserve import paths and existing working commands.
- A new directory is justified only if it has a distinct, lasting responsibility and more than a one-off file. Name it by responsibility, not by CLI, date, or temporary workaround.

## 2. One responsibility, one canonical home

- **Framework implementation:** existing source package (target: `src/`). Synthesis, Independent Test, Challenge, Controller, Repair, validation, and orchestration share ONE implementation each.
- **Framework tests:** `tests/`. These test the harness, not generated Terminal-Bench tasks.
- **Task specifications:** `specs/`. Human-provided or versioned Plans/Contracts; treat frozen versions as immutable.
- **Evaluation fixtures:** `benchmarks/`. Fixed correct/invalid controls and held-out cases, separated by task type.
- **Experiment scripts/configs:** `experiments/<experiment>/`. Thin entry points and analysis only; import shared framework code.
- **Per-run output:** `runs/<experiment>/<run_id>/`. Candidate files, generated tests, challenge witnesses, logs, intermediate validation, cost records.
- **Accepted exports:** `artifacts/accepted/<task_id>/`, only after the defined acceptance checks; record the exact provenance and network mode.
- **Human-readable conclusions:** `reports/`. Do not dump raw run output here.
- **Engineering notes:** `docs/`; reusable utility commands: `scripts/`.

Never put generated tasks/tests/logs into `src/`, put production implementation into `experiments/`, or use one file as both a frozen fixture and mutable working output.

## 3. Keep Step 1/2/3 as experiments, not forks

- Step 1 (`01_e2e_reliability`): run a frozen code/config/budget from a new Plan/Contract; verify unattended native acceptance and repeat frozen validations.
- Step 2 (`02_general_repair`): modify the shared Synthesis/Controller/Repair code; evaluate task-agnostic behavior on CSV, JSONL, and manifest tasks. Never add a CSV-specific fix to generic logic merely to make one run pass without explicitly documenting and isolating it.
- Step 3 (`03_test_challenge_eval`): compare the baseline, improved Test, and Test+Challenge under a consistent protocol; protect held-out cases from repair feedback.
- All three use shared code; results live in separate `runs/` subfolders and summaries in `reports/`.

## 4. Multiple CLI sessions and Git worktrees

- Multiple *writing* CLI sessions must not edit the same checkout simultaneously. Use a dedicated Git worktree and task branch for parallel work, or assign strictly disjoint files with a single integrator.
- Each session owns a stated scope. Before touching shared files (Controller, schemas, validation, public interfaces), check and coordinate with the integrator.
- Integrate code through reviewed commits (`cherry-pick` or merge), not `cp`/`rsync` of entire worktree directories.
- Untracked files are **not** moved by Git merges/cherry-picks. Inspect `git status --short`; explicitly stage intentional new source/tests/docs in the source branch before handoff. Do not indiscriminately copy every untracked file.
- Never use destructive `git reset --hard`, `git clean -fd`, force push, or overwrite another session's files without explicit approval. Do not push or merge into the shared main branch without authorization.

## 5. Experiments must be reproducible and non-destructive

- Each new run has a unique `run_id` and its own output directory; never overwrite a previous run or its frozen inputs, tests, witnesses, or review evidence.
- Preserve abandoned candidates and failure evidence. If two consecutive candidates fail for the same reason category, pause automatic retries for diagnosis instead of blindly spending more calls.
- Record: Git commit/dirty state, task/spec ID and hashes, model/config, model-call and token budget, runner settings (including Docker/Harbor network mode), execution results, failure reasons, repair count, and acceptance decision.
- Keep baseline and held-out evaluation fixtures immutable during a run. Separate data used for feedback/repair from data used for final evaluation; a directory name alone is NOT a security boundary—enforce access in agent tools and permissions.
- Preserve distinctions between `PASS`, assertion rejection, execution error, not run, and unresolved. Never relabel a skipped/null/error case as successful rejection.
- A task is `Accepted` only if the native Controller and all required validation conditions really pass; a later frozen revalidation must be distinguished from an uninterrupted end-to-end run. Report public-network Harbor validation as such, not as strict no-network validation.

## 6. Repair and responsibility boundaries

- Independent Test generation must not read Reference Solution or Synthesis Probe. Challenge may create its own invalid implementation and witness but cannot edit frozen tests.
- Test/Probe/Solution failures need evidence-based attribution. Repair proposals do not authorize modifications by themselves; Controller/host checks decide permissions and scope.
- After a repair, rerun the required controls and regression checks; never weaken tests merely to obtain `PASS`.
- Reuse generic execution-feedback mechanisms. Task-specific examples and fixtures belong in `benchmarks/`, not scattered conditionals in the framework.

## 7. Deliver clean changes

- Prefer small, reviewable changes and reuse existing names. Avoid `final_v2`, `new_new`, `backup`, date-stamped source files, and parallel implementations.
- Keep run logs, temporary containers, caches, generated large files, and secrets out of ordinary Git commits; maintain appropriate `.gitignore` patterns. Review files before sharing a run or report.
- Do not silently change the experimental protocol, acceptance criteria, Plan/Contract, frozen tests, or held-out sets.
- Before handoff: state what changed, where it changed, what commands/tests ran and their actual results, any unresolved blockers, new/changed files, and whether a commit was created. If tests did not run, say so.

## Root Directory Policy

The repository root must remain minimal and stable.

- Do not create new top-level directories for individual experiments, development steps, CLI sessions, temporary workspaces, or debugging attempts.
- New experiments belong under `experiments/`, and their outputs belong under `runs/`.
- Permanent implementation code belongs in the existing package or an established shared module.
- Historical artifacts belong in the designated archive locations.
- New top-level directories require an explicit architectural justification and user approval.
- Before creating a directory, inspect existing locations and reuse them when their responsibilities match.
- Do not move existing source modules, Git worktrees, or frozen evidence solely to satisfy the preferred layout.
- Use Git commits and tags for code versioning, Experiment IDs for experimental definitions, and Run IDs for individual executions. Do not create directory copies to represent versions.