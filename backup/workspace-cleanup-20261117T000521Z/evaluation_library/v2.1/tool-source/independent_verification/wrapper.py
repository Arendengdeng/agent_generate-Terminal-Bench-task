"""Trusted standalone pytest wrapper, copied into /tests as run_tests.py.

This classifies ordinary task assertions, not malicious verifier code. Challenge
testing remains a separate stage. No generated code is executed on the host.
"""
import argparse
import json
import os
import re
from pathlib import Path
import sys
import time
import subprocess


def artifact_snapshot(spec):
    import base64, os, pathlib, stat
    files = {}; directories = set(); total = 0
    def inspect(path):
        nonlocal total
        p=pathlib.Path(path)
        assert p.is_absolute() and '..' not in p.parts and p.parts[1]=='app'
        for parent in [*reversed(p.parents),p]:
            st=os.lstat(parent)
            if stat.S_ISLNK(st.st_mode): raise ValueError('symlink in artifact path')
        if stat.S_ISDIR(st.st_mode):
            directories.add(str(p))
            for child in sorted(p.iterdir()): inspect(child)
        else:
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1: raise ValueError('non-ordinary artifact')
            if str(p) in files: return
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as f:
                opened=os.fstat(f.fileno())
                if (opened.st_ino,opened.st_dev)!=(st.st_ino,st.st_dev): raise ValueError('artifact changed')
                raw=f.read(spec['file_limit']+1)
            total+=len(raw)
            if len(raw)>spec['file_limit'] or total>spec['total_limit'] or len(files)>=spec['count_limit']:
                raise ValueError('artifact budget exceeded')
            files[str(p)]=base64.b64encode(raw).decode()
    for path in spec['paths']:
        inspect(path)
    return {'files': files, 'directories': sorted(directories)}


def feedback_message(value, limit=2000):
    """Omit private Python traceback frames; never include captured solve logs."""
    value = str(value)
    value = re.sub(r'(?m)^\s*File ["\']/(?:app|solution)/[^\n]*\n(?:[^\n]*\n)?',
                   '[private application frame omitted]\n', value)
    return value[:limit]


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
                self.commands, self.current_node = [], None

            def pytest_runtest_logstart(self, nodeid, location):
                self.current_node = nodeid

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
                exception = None
                if call.excinfo:
                    frames = []
                    for entry in call.excinfo.traceback:
                        path = Path(str(entry.path)).absolute()
                        if path.parent == root and path.name.startswith('test_'):
                            lines = path.read_text(encoding='utf-8').splitlines()
                            frames.append({'path': path.name, 'line': entry.lineno + 1,
                                           'source': lines[entry.lineno][:1000] if entry.lineno < len(lines) else ''})
                    exception = {'type': call.excinfo.typename,
                                 'message': feedback_message(call.excinfo.value),
                                 'test_traceback': frames[-8:]}
                self.reports.append({"nodeid": result.nodeid, "when": result.when,
                                     "outcome": result.outcome, "task_assertion": assertion,
                                     "exception": exception,
                                     'stdout': feedback_message(result.capstdout, 8000),
                                     'stderr': feedback_message(result.capstderr, 8000),
                                     'duration_sec': result.duration,
                                     'commands': [c for c in self.commands if c['nodeid'] == result.nodeid] if result.when == 'call' else [],
                                     "xfail": bool(hasattr(result, "wasxfail") or item.get_closest_marker("xfail"))})

        os.chdir(root)
        recorder = Recorder()
        if not args.collect:
            expected_spec = json.loads((root / 'expected.json').read_text())
            if 'artifact_policy' in expected_spec:
                artifacts = artifact_snapshot(expected_spec['artifact_policy'])
                report['artifact_manifest'] = {p: __import__('hashlib').sha256(
                    __import__('base64').b64decode(v)).hexdigest() for p, v in artifacts['files'].items()}
        tests = sorted(p.name for p in root.glob("test_*.py"))
        if not tests:
            raise ValueError("no test files")
        options = ["-q", "-c", "/dev/null", "--rootdir", str(root), "--confcutdir", str(root),
                   "--noconftest", "-p", "no:cacheprovider", *tests]
        if args.collect:
            options.append("--collect-only")
        started = time.monotonic()
        original_run = subprocess.run
        def observed_run(*positional, **keywords):
            try:
                completed = original_run(*positional, **keywords)
            except subprocess.TimeoutExpired as exc:
                recorder.commands.append({'nodeid': recorder.current_node, 'status': 'timeout',
                                          'stdout': feedback_message(exc.stdout or '', 64000),
                                          'stderr': feedback_message(exc.stderr or '', 64000)})
                raise
            if recorder.current_node:
                def stream(value):
                    if isinstance(value, bytes):
                        value = value.decode('utf-8', errors='replace')
                    value = str(value or '')
                    if len(value) > 64000:
                        recorder.errors.append('command output evidence limit exceeded')
                    return feedback_message(value, 64000)
                recorder.commands.append({'nodeid': recorder.current_node, 'status': 'completed',
                                          'returncode': completed.returncode,
                                          'stdout': stream(completed.stdout), 'stderr': stream(completed.stderr)})
            return completed
        subprocess.run = observed_run
        try:
            code = int(pytest.main(options, plugins=[recorder]))
        finally:
            subprocess.run = original_run
        if args.collect:
            ok = code == 0 and recorder.nodeids and not recorder.errors and len(set(recorder.nodeids)) == len(recorder.nodeids)
            report = {"status": "completed" if ok else "error", "nodeids": recorder.nodeids,
                      "pytest_exit_code": code, "error": recorder.errors or (None if ok else "invalid collection")}
        else:
            expected = json.loads((root / "expected.json").read_text())["nodeids"]
            artifact_manifest = report.get('artifact_manifest')
            report = classify(code, recorder.nodeids, recorder.reports, recorder.errors, expected)
        if not args.collect and 'artifact_manifest' in locals():
            report['artifact_manifest'] = artifact_manifest
        report['wall_sec'] = round(time.monotonic() - started, 6)
    except BaseException as exc:
        report.update(status="error", reward=None, error=f"{type(exc).__name__}: {exc}")
    name = "collection.json" if args.collect else "execution.json"
    (log / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.collect and report["status"] == "completed":
        (log / "reward.txt").write_text(str(report["reward"]) + "\n")
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
