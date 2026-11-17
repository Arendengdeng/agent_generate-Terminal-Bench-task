# CSV assertion audit

Frozen tests: runs/step3-live-01/test-agent/tests. No production or frozen test files changed.

Two handwritten CLI implementations were run against the same frozen 15 tests in disposable Docker containers using independent-verifier:pytest-9.2.0. They use the same csv.reader, normalization, stable deduplication, header and input handling. Only body writer quoting differs: QUOTE_MINIMAL versus QUOTE_ALL. Header remains unquoted in both variants, avoiding ambiguity in the phrase 'header email,name'.

Results: minimal passes 15/15, reward=1. Quoted body passes 14/15, reward=0. Sole failure: test_stdlib.py::test_script_works_with_only_stdlib_importable, line 31. Actual CSV row '"a@b.c","N"' is compared to raw 'a@b.c,N', although parsed fields are identical. Execution and stdout evidence are preserved alongside summary.json and the exact implementation variants.

Findings:
- Direct cause confirmed: test_stdlib.py compares serialized lines instead of parsed CSV fields. The dependency test unnecessarily adds a serialization constraint.
- Test suite inconsistency confirmed: test_clean.py already uses csv.reader and assert_output, while the later stdlib test duplicates output validation with splitlines/raw strings. Trace shows this test was written at model call 8 and rewritten at call 9. The trace does not establish the model's internal reasoning.
- Prompt gap: agent.py asks for public behavior and forbids extra requirements, but does not explicitly distinguish semantic equality from byte equality or require reuse of output comparison helpers. This is a plausible contributor, not a proven internal cause.
- Completion gate checks collection/digest and Requirement-to-Test Mapping only. These do not detect overconstraints. The new stdlib test maps to R4, yet its extra content assertion can reject compliant CSV serialization.
- Oracle/Nop cannot reveal this defect when the Oracle uses the accepted serialization. No alternative known-correct solution was supplied in the prior Harbor acceptance.

Contract and Instruction require CSV escaping and correct field values, with no requirement that data fields use minimal quoting. Single sample evidence cannot estimate defect frequency or establish whole-architecture failure.

Suggested repair: parse CSV in all format-semantic assertions, preserve -I/-S subprocess checks for stdlib-only requirements, then confirm both variants pass. Add serialization-equivalence guidance and consider reviewing extra assertions beyond requirement-to-test IDs. Any revised tests must be versioned and revalidated, not silently replace the accepted frozen suite.
