#!/usr/bin/env python3
"""Behavioral self-check for the JSONL summarize repair task."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
SCRIPT = os.path.join(APP, "summarize.py")
SOLUTION = "/solution"


def _find_solution_script():
    for name in ("summarize.py", "solve.sh"):
        p = os.path.join(SOLUTION, name)
        if os.path.isfile(p):
            return p
    raise AssertionError("no solution artifact found in /solution")


def _run(app_dir, input_path, output_path):
    return subprocess.run(
        [sys.executable, os.path.join(app_dir, "summarize.py"), input_path, output_path],
        cwd="/tmp",
        timeout=COMMAND_TIMEOUT_SEC,
        capture_output=True,
        text=True,
    )


def _write_input(tmpdir, name, records):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _expected(records):
    agg = {}
    for rec in records:
        key = (rec["service"], rec["level"])
        count, total = agg.get(key, (0, 0))
        agg[key] = (count + 1, total + rec["duration_ms"])
    rows = []
    for (service, level) in sorted(agg):
        count, total = agg[(service, level)]
        rows.append(
            {
                "service": service,
                "level": level,
                "count": count,
                "total_duration_ms": total,
            }
        )
    return rows


def _assert_shape(rows):
    assert isinstance(rows, list), "output must be a JSON array, got %r" % (rows,)
    for row in rows:
        assert isinstance(row, dict), "each element must be a JSON object, got %r" % (row,)
        assert set(row.keys()) == {"service", "level", "count", "total_duration_ms"}, (
            "element keys wrong: %r" % (sorted(row.keys()),)
        )
        assert isinstance(row["service"], str) and row["service"], "bad service %r" % (row["service"],)
        assert row["level"] in ("INFO", "WARN", "ERROR"), "bad level %r" % (row["level"],)
        assert isinstance(row["count"], int) and not isinstance(row["count"], bool), "bad count %r" % (row["count"],)
        assert row["count"] > 0, "count must be positive: %r" % (row["count"],)
        assert isinstance(row["total_duration_ms"], int) and not isinstance(
            row["total_duration_ms"], bool
        ), "bad total_duration_ms %r" % (row["total_duration_ms"],)
        assert row["total_duration_ms"] >= 0, "total must be non-negative"


def _run_case(app_dir, tmpdir, records, name):
    inp = _write_input(tmpdir, name + ".jsonl", records)
    out = os.path.join(tmpdir, name + ".out.json")
    result = _run(app_dir, inp, out)
    assert result.returncode == 0, "nonzero exit %r stderr=%r" % (result.returncode, result.stderr)
    assert os.path.isfile(out), "no output file produced for %s" % name
    with open(out, "r", encoding="utf-8") as fh:
        raw = fh.read()
    rows = json.loads(raw)
    _assert_shape(rows)
    assert rows == _expected(records), "%s mismatch: got %r" % (name, rows)
    return rows, inp, out, raw


def _check_r1(app_dir):
    tmpdir = tempfile.mkdtemp(dir="/tmp")
    try:
        records = [
            {"service": "api", "level": "ERROR", "duration_ms": 12},
            {"service": "api", "level": "ERROR", "duration_ms": 8},
            {"service": "web", "level": "INFO", "duration_ms": 0},
        ]
        out = os.path.join(tmpdir, "r1.json")
        inp = _write_input(tmpdir, "r1.jsonl", records)
        result = _run(app_dir, inp, out)
        assert result.returncode == 0, "nonzero exit: %r stderr=%r" % (result.returncode, result.stderr)
        assert os.path.isfile(out), "output file not created"
        with open(out, "r", encoding="utf-8") as fh:
            rows = json.loads(fh.read())
        _assert_shape(rows)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _check_r2(app_dir):
    tmpdir = tempfile.mkdtemp(dir="/tmp")
    try:
        records = []
        # exact duplicate records must all be counted
        for _ in range(4):
            records.append({"service": "api", "level": "WARN", "duration_ms": 5})
        records.append({"service": "api", "level": "WARN", "duration_ms": 0})
        records.append({"service": "api", "level": "ERROR", "duration_ms": 1000})
        records.append({"service": "api", "level": "INFO", "duration_ms": 1})
        records.append({"service": "web", "level": "INFO", "duration_ms": 7})
        records.append({"service": "web", "level": "INFO", "duration_ms": 3})
        rows, _, _, _ = _run_case(app_dir, tmpdir, records, "r2")
        by_key = {(r["service"], r["level"]): r for r in rows}
        assert by_key[("api", "WARN")]["count"] == 5, "duplicate records lost: %r" % (by_key[("api", "WARN")],)
        assert by_key[("api", "WARN")]["total_duration_ms"] == 20, "warn total wrong"
        assert by_key[("api", "ERROR")]["total_duration_ms"] == 1000, "error total wrong"
        assert by_key[("api", "INFO")]["count"] == 1, "level mixing detected"
        assert by_key[("web", "INFO")]["total_duration_ms"] == 10, "web total wrong"
        assert len(rows) == 4, "wrong group count: %r" % (len(rows),)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _check_r3(app_dir):
    tmpdir = tempfile.mkdtemp(dir="/tmp")
    try:
        # empty file
        inp = os.path.join(tmpdir, "empty.jsonl")
        open(inp, "w", encoding="utf-8").close()
        out = os.path.join(tmpdir, "empty.json")
        result = _run(app_dir, inp, out)
        assert result.returncode == 0, "nonzero exit on empty input: %r" % (result.stderr,)
        with open(out, "r", encoding="utf-8") as fh:
            assert json.loads(fh.read()) == [], "empty input must yield []"

        # ordering + only present groups + unicode service names
        records = [
            {"service": "Zeta", "level": "INFO", "duration_ms": 1},
            {"service": "Zeta", "level": "ERROR", "duration_ms": 2},
            {"service": "alpha", "level": "WARN", "duration_ms": 3},
            {"service": "alpha", "level": "INFO", "duration_ms": 4},
            {"service": "订单", "level": "ERROR", "duration_ms": 5},
            {"service": "订单", "level": "INFO", "duration_ms": 6},
            {"service": "支付-β", "level": "WARN", "duration_ms": 7},
            {"service": "支付-β", "level": "ERROR", "duration_ms": 0},
        ]
        rows, _, _, _ = _run_case(app_dir, tmpdir, records, "r3")
        pairs = [(r["service"], r["level"]) for r in rows]
        assert pairs == sorted(pairs), "groups not sorted: %r" % (pairs,)
        assert set(pairs) == {(r["service"], r["level"]) for r in records}, "unexpected/missing groups"

        # different input file -> different result (no stale state)
        records2 = [{"service": "solo", "level": "ERROR", "duration_ms": 9}]
        rows2, _, _, _ = _run_case(app_dir, tmpdir, records2, "r3b")
        assert len(rows2) == 1 and rows2[0]["service"] == "solo", "second run wrong: %r" % (rows2,)

        # boundary: max duration value
        big = [{"service": "big", "level": "INFO", "duration_ms": 10 ** 12}]
        rows3, _, _, _ = _run_case(app_dir, tmpdir, big, "r3c")
        assert rows3[0]["total_duration_ms"] == 10 ** 12, "large duration wrong"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _check_r4(app_dir):
    tmpdir = tempfile.mkdtemp(dir="/tmp")
    try:
        records = [
            {"service": "api", "level": "INFO", "duration_ms": 1},
            {"service": "api", "level": "ERROR", "duration_ms": 2},
            {"service": "web", "level": "WARN", "duration_ms": 3},
        ]
        inp = _write_input(tmpdir, "r4.jsonl", records)
        os.chmod(inp, 0o644)
        before = _read_bytes(inp)
        st_before = os.stat(inp)
        out = os.path.join(tmpdir, "r4.json")
        result = _run(app_dir, inp, out)
        assert result.returncode == 0, "nonzero exit: %r" % (result.stderr,)
        after = _read_bytes(inp)
        st_after = os.stat(inp)
        assert before == after, "input file content modified"
        assert st_before.st_size == st_after.st_size, "input file size changed"

        with open(SCRIPT, "r", encoding="utf-8") as fh:
            src = fh.read()
        for banned in ("import requests", "import numpy", "import pandas", "subprocess", "socket"):
            assert banned not in src, "disallowed dependency/behaviour: %s" % banned

        files = sorted(os.listdir(APP))
        assert files == ["summarize.py"], "extra files delivered in /app: %r" % (files,)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


CHECKS = {
    "R1": _check_r1,
    "R2": _check_r2,
    "R3": _check_r3,
    "R4": _check_r4,
}


def check(requirement_id):
    if requirement_id not in CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    CHECKS[requirement_id](APP)


if __name__ == "__main__":
    for rid in CHECKS:
        check(rid)
        print("ok", rid)
