"""Trusted standalone pytest wrapper, copied into /tests as run_tests.py.

This classifies ordinary task assertions, not malicious verifier code. Challenge
testing remains a separate stage. No generated code is executed on the host.
"""
import argparse
import json
import os
from pathlib import Path
import sys


def classify(exit_code, collected, reports, errors, expected):
    error = list(errors)
    if not collected or len(collected) != len(set(collected)):
        error.append("empty or duplicate collection")
    if set(collected) != set(expected) or len(expected) != len(set(expected)):
        error.append("collection differs from frozen expected tests")
    if exit_code not in (0, 1):
        error.append(f"pytest exit code {exit_code}")
    failed = False
    for nodeid in collected:
        phases = [r for r in reports if r["nodeid"] == nodeid]
        stage_names = [r["when"] for r in phases]
        if len(stage_names) != len(set(stage_names)) or any(s not in {"setup", "call", "teardown"} for s in stage_names):
            error.append(f"duplicate or unexpected phase: {nodeid}")
        by_stage = {r["when"]: r for r in phases}
        if "setup" not in by_stage or "teardown" not in by_stage:
            error.append(f"incomplete phases: {nodeid}")
        elif by_stage["setup"]["outcome"] == "passed" and "call" not in by_stage:
            error.append(f"missing call: {nodeid}")
        for row in phases:
            if row["outcome"] not in {"passed", "failed", "skipped"}:
                error.append(f"invalid outcome: {nodeid}")
            if row["outcome"] == "skipped" or row.get("xfail"):
                error.append(f"skip/xfail is not valid evidence: {nodeid}")
            elif row["outcome"] == "failed":
                if row.get("task_assertion") and row["when"] in {"setup", "call"}:
                    failed = True
                else:
                    error.append(f"verifier exception: {nodeid} ({row['when']})")
    if any(r["nodeid"] not in collected for r in reports):
        error.append("unexpected test reports")
    if exit_code == 0 and failed or exit_code == 1 and not failed:
        error.append("pytest exit code and phase reports disagree")
    return {"status": "error" if error else "completed", "pytest_exit_code": exit_code,
            "reward": None if error else int(not failed), "error": error or None,
            "nodeids": collected, "results": reports}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--report-dir", default="/logs/verifier")
    args = parser.parse_args(argv)
    root = Path(__file__).absolute().parent
    log = Path(args.report_dir)
    log.mkdir(parents=True, exist_ok=True)
    for name in ("reward.txt", "execution.json", "collection.json"):
        (log / name).unlink(missing_ok=True)
    report = {"status": "error", "pytest_exit_code": None, "reward": None, "error": None}
    try:
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        os.environ.pop("PYTEST_ADDOPTS", None)
        os.environ.pop("PYTEST_PLUGINS", None)
        import pytest

        class Recorder:
            def __init__(self):
                self.nodeids, self.reports, self.errors = [], [], []

            def pytest_collection_finish(self, session):
                self.nodeids = [item.nodeid for item in session.items]

            def pytest_collectreport(self, report):
                if report.failed or report.skipped:
                    self.errors.append("collection failed or skipped: " + report.nodeid)

            def pytest_internalerror(self, excrepr, excinfo):
                self.errors.append("pytest internal error")

            @pytest.hookimpl(hookwrapper=True)
            def pytest_runtest_makereport(self, item, call):
                outcome = yield
                result = outcome.get_result()
                assertion = bool(call.excinfo and isinstance(call.excinfo.value, (AssertionError, pytest.fail.Exception)))
                self.reports.append({"nodeid": result.nodeid, "when": result.when,
                                     "outcome": result.outcome, "task_assertion": assertion,
                                     "xfail": bool(hasattr(result, "wasxfail") or item.get_closest_marker("xfail"))})

        os.chdir(root)
        recorder = Recorder()
        tests = sorted(p.name for p in root.glob("test_*.py"))
        if not tests:
            raise ValueError("no test files")
        options = ["-q", "-c", "/dev/null", "--rootdir", str(root), "--confcutdir", str(root),
                   "--noconftest", "-p", "no:cacheprovider", *tests]
        if args.collect:
            options.append("--collect-only")
        code = int(pytest.main(options, plugins=[recorder]))
        if args.collect:
            ok = code == 0 and recorder.nodeids and not recorder.errors and len(set(recorder.nodeids)) == len(recorder.nodeids)
            report = {"status": "completed" if ok else "error", "nodeids": recorder.nodeids,
                      "pytest_exit_code": code, "error": recorder.errors or (None if ok else "invalid collection")}
        else:
            expected = json.loads((root / "expected.json").read_text())["nodeids"]
            report = classify(code, recorder.nodeids, recorder.reports, recorder.errors, expected)
    except BaseException as exc:
        report.update(status="error", reward=None, error=f"{type(exc).__name__}: {exc}")
    name = "collection.json" if args.collect else "execution.json"
    (log / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.collect and report["status"] == "completed":
        (log / "reward.txt").write_text(str(report["reward"]) + "\n")
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
