# General execution-feedback repair

`--repair` defaults to `execution-feedback-v1`; `--repair-policy host-contract-evidence-v1` retains deterministic proof-based authorization for comparisons. Existing test-only and Challenge paths retain their original policy.

The shared evidence envelope lives in `synthesis_agent.feedback`. It represents typed observations rather than a fixed task input/output schema. Host projections omit private implementations and held-out results. Investigators can read authorized evidence/source in chunks and run bounded commands in fresh no-network public sandboxes.

An investigator proposes components, a complete Requirement quotation, current evidence, expected change and validation plan. The host checks version/digest bindings and component scopes; `trial_authorized` explicitly leaves semantic blame unconfirmed. Solution/Probe repair uses Synthesis permissions. Test repair sees only public inputs and development evidence. Mixed proposals execute in one versioned trial, with public-input changes rebinding metadata without changing frozen test content.

Generic investigation may use multiple read-only calls per response and shares the global model/tool budgets with patching. The legacy `max_diagnosis_calls` one-shot limit does not apply to this interactive phase; context/completion limits still apply. Repair starts with a compact execution summary and the approved diagnosis; detailed evidence stays available by ID instead of being duplicated into multiple prompt fields.

Investigation can span multiple rounds. `record_hypothesis` records provisional components, supporting evidence and a next check without finishing analysis or enabling writes. The Agent may revise or abandon these hypotheses after additional source reads or sandbox checks. Only a final `propose_repair` enters host authorization; uncertainty can remain unresolved when the shared budget is exhausted. Hypothesis history is preserved with the final diagnosis and investigation records.

A structurally rejected development-test patch is preserved as a rejected attempt. Its reason and bounded diff return to investigation while the original candidate/tests remain current; no new task version is promoted. Re-investigation and subsequent trial repairs share the original call/repair budgets. Two patch rejections stop automatic retries. Offline review replays the rejection and verifies the preserved rejected files as well as the eventual accepted trial.

The investigator receives the task lifecycle explicitly: the initial application is intentionally faulty, Nop should be rejected, and Oracle applies a separate private reference repair. Expected baseline failures alone are not reasons to alter the Solution or initial environment. This is a framework invariant, not a task-specific semantic rule.

Development patches must retain existing nodes, behavioral checks and Requirement mappings, and cannot add skips or broad exception handlers. These are structural guards, not proof of semantic preservation. Every trial reruns the full development control matrix; final acceptance uses separate frozen tests and terminal held-out evaluation with repairs disabled. A bad frozen suite remains a blocker. Missing correct/invalid feedback controls block automatic test repair.

The Controller records regressions, budgets and unresolved issues. Two consecutive versions with the same broad failure category pause retries. Static package failures retain the existing deterministic Synthesis path. Final offline review rechecks authorization, scope, patch guards, test/control digests, frozen verifier content and actual native validation reports.

Docker and diagnostic sandboxes disable networking. Existing Harbor exports use public networking and are reported as such. Services, package installation and host configuration remain outside this revision.

The `02_general_repair` experiment compares policies through the existing CLI. Frozen input/source signatures are checked before and after each trial; progress is append-only. Separate repeated transfer experiments are required before claiming task generality. See the experiment protocol and per-run reports for actual outcomes.
