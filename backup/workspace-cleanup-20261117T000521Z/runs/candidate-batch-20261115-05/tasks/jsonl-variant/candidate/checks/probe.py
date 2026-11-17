"""Behavioral probe for the JSONL service aggregation task.

Checks are performed by running the CLI in /app:
    python /app/summarize.py <input.jsonl> <output.json>
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

APP = "/app"
SCRIPT = os.path.join(APP, "summarize.py")
COMMAND_TIMEOUT_SEC = 10

REQUIREMENTS = ("R1", "R2", "R3", "R4")


def _run(inp, out):
    return subprocess.run(
        [sys.executable, SCRIPT, inp, out],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _write_lines(text):
    fd, path = tempfile.mkstemp(prefix="probe_in_", suffix=".jsonl", dir="/tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _out_path():
    fd, path = tempfile.mkstemp(prefix="probe_out_", suffix=".json", dir="/tmp")
    os.close(fd)
    return path


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _aggregate(records):
    groups = {}
    for rec in records:
        svc = rec["service"]
        dur = rec["duration_ms"]
        if svc not in groups:
            groups[svc] = {"count": 0, "total": 0, "max": dur}
        groups[svc]["count"] += 1
        groups[svc]["total"] += dur
        if dur > groups[svc]["max"]:
            groups[svc]["max"] = dur
    return [
        {
            "service": svc,
            "count": groups[svc]["count"],
            "total_duration_ms": groups[svc]["total"],
            "max_duration_ms": groups[svc]["max"],
        }
        for svc in sorted(groups)
    ]


def _to_jsonl(records):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def _assert_report(records, label):
    inp = _write_lines(_to_jsonl(records))
    out = _out_path()
    try:
        proc = _run(inp, out)
        assert proc.returncode == 0, (
            "%s: non-zero exit %r stderr=%r" % (label, proc.returncode, proc.stderr)
        )
        assert os.path.exists(out), "%s: output file not created" % label
        with open(out, "r", encoding="utf-8") as handle:
            text = handle.read()
        try:
            data = json.loads(text)
        except ValueError as exc:  # pragma: no cover - reported as failure
            raise AssertionError("%s: output is not valid JSON: %r (%s)" % (label, text, exc))
        expected = _aggregate(records)
        assert isinstance(data, list), "%s: output is not a JSON array: %r" % (label, data)
        got_norm = []
        for item in data:
            assert isinstance(item, dict), "%s: non-object element %r" % (label, item)
            assert set(item.keys()) == {
                "service",
                "count",
                "total_duration_ms",
                "max_duration_ms",
            }, "%s: wrong keys %r" % (label, sorted(item.keys()))
            got_norm.append(item)
        assert got_norm == expected, "%s: report mismatch\n got=%r\n want=%r" % (
            label,
            got_norm,
            expected,
        )
    finally:
        for path in (inp, out):
            try:
                os.unlink(path)
            except OSError:
                pass


def _check_r1():
    records = [
        {"service": "api", "level": "INFO", "duration_ms": 10},
        {"service": "web", "level": "WARN", "duration_ms": 3},
    ]
    _assert_report(records, "r1-small")
    _assert_report(
        [{"service": "solo", "level": "ERROR", "duration_ms": 0}], "r1-single"
    )


def _check_r2():
    records = [
        {"service": "api", "level": "INFO", "duration_ms": 10},
        {"service": "api", "level": "WARN", "duration_ms": 25},
        {"service": "api", "level": "ERROR", "duration_ms": 5},
        {"service": "api", "level": "INFO", "duration_ms": 10},
        {"service": "api", "level": "INFO", "duration_ms": 10},
        {"service": "web", "level": "ERROR", "duration_ms": 100},
        {"service": "web", "level": "ERROR", "duration_ms": 100},
        {"service": "web", "level": "INFO", "duration_ms": 1},
    ]
    _assert_report(records, "r2-multi-level")
    # interleaved services with duplicate records
    interleaved = []
    for i in range(20):
        interleaved.append({"service": "svc-%d" % (i % 3), "level": ["INFO", "WARN", "ERROR"][i % 3], "duration_ms": i})
    _assert_report(interleaved, "r2-interleaved")


def _check_r3():
    records = [
        {"service": "\u670d\u52a1-\u4e59", "level": "INFO", "duration_ms": 4},
        {"service": "\u670d\u52a1-\u7532", "level": "WARN", "duration_ms": 9},
        {"service": "Zeta", "level": "ERROR", "duration_ms": 1},
        {"service": "Alpha", "level": "INFO", "duration_ms": 2},
        {"service": "alpha", "level": "INFO", "duration_ms": 6},
        {"service": "__x", "level": "INFO", "duration_ms": 3},
    ]
    _assert_report(records, "r3-unicode-order")
    _assert_report([], "r3-empty")

    # alternative input: only a subset of the services appears
    _assert_report(
        [{"service": "only", "level": "WARN", "duration_ms": 7}], "r3-only-present"
    )

    # empty file written with no bytes at all
    inp = _write_lines("")
    out = _out_path()
    try:
        proc = _run(inp, out)
        assert proc.returncode == 0, "r3-empty-file: exit %r" % (proc.returncode,)
        with open(out, "r", encoding="utf-8") as handle:
            assert json.load(handle) == [], "r3-empty-file: expected []"
    finally:
        for path in (inp, out):
            try:
                os.unlink(path)
            except OSError:
                pass


def _check_r4():
    records = [
        {"service": "keep", "level": "INFO", "duration_ms": 11},
        {"service": "keep", "level": "ERROR", "duration_ms": 11},
    ]
    inp = _write_lines(_to_jsonl(records))
    out = _out_path()
    try:
        before = _sha(inp)
        proc = _run(inp, out)
        assert proc.returncode == 0, "r4: exit %r" % (proc.returncode,)
        assert _sha(inp) == before, "r4: input file was modified"
    finally:
        for path in (inp, out):
            try:
                os.unlink(path)
            except OSError:
                pass

    # only summarize.py is delivered; no other files needed beyond stdlib
    assert os.path.isfile(SCRIPT), "r4: /app/summarize.py missing"
    code = (
        "import runpy, sys\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='not_main')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-S", "-c", code, SCRIPT],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
        cwd="/tmp",
    )
    assert proc.returncode == 0, "r4: stdlib-only import failed: %r" % (proc.stderr,)
    third_party = sorted(
        {"numpy", "pandas", "orjson", "ujson"} & set(
            line.split(".")[0].strip()
            for line in proc.stderr.splitlines()
        )
    )
    assert not third_party, "r4: unexpected third-party usage %r" % (third_party,)


def check(requirement_id):
    if requirement_id not in REQUIREMENTS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    globals()["_check_" + requirement_id.lower()]()
