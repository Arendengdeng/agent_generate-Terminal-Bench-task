"""Tests for the JSONL aggregation CLI /app/summarize.py."""

import json
import os
import shutil
import subprocess
import sys

import pytest

APP = "/app/summarize.py"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10

FIELDS = {"service", "level", "count", "total_duration_ms"}


def run_cli(inp, out, timeout=TIMEOUT):
    return subprocess.run(
        [sys.executable, APP, inp, out],
        cwd="/app",
        capture_output=True,
        timeout=timeout,
    )


def load_output(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def assert_structure(rows):
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        assert set(row.keys()) == FIELDS, row
        assert isinstance(row["service"], str) and row["service"] != ""
        assert row["level"] in ("INFO", "WARN", "ERROR")
        assert isinstance(row["count"], int) and not isinstance(row["count"], bool)
        assert row["count"] >= 1
        assert isinstance(row["total_duration_ms"], int) and not isinstance(
            row["total_duration_ms"], bool
        )
        assert row["total_duration_ms"] >= 0


def as_map(rows):
    return {(r["service"], r["level"]): (r["count"], r["total_duration_ms"]) for r in rows}


def expected_map(records):
    agg = {}
    for rec in records:
        key = (rec["service"], rec["level"])
        count, total = agg.get(key, (0, 0))
        agg[key] = (count + 1, total + rec["duration_ms"])
    return agg


def read_fixture(name):
    records = []
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def copy_fixture(name, tmp_path):
    src = os.path.join(FIXTURES, name)
    dst = tmp_path / ("input_" + name)
    shutil.copyfile(src, dst)
    return str(dst)


def test_basic_grouping_counts_and_sums(tmp_path):
    inp = copy_fixture("basic.jsonl", tmp_path)
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    assert out.exists(), "output file not written"
    rows = load_output(str(out))
    assert_structure(rows)
    records = read_fixture("basic.jsonl")
    assert as_map(rows) == expected_map(records)
    assert as_map(rows)[("alpha", "INFO")] == (3, 40)


def test_output_sorted_by_service_then_level(tmp_path):
    inp = copy_fixture("unicode.jsonl", tmp_path)
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    assert_structure(rows)
    keys = [(r["service"], r["level"]) for r in rows]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)), "duplicate groups in output"
    # Only observed groups, all of them.
    assert set(keys) == set(expected_map(read_fixture("unicode.jsonl")))


def test_unicode_and_mixed_case_services(tmp_path):
    inp = copy_fixture("unicode.jsonl", tmp_path)
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    mapping = as_map(rows)
    assert mapping[("订单服务", "ERROR")] == (2, 199)
    assert mapping[("订单服务", "INFO")] == (1, 50)
    assert mapping[("Apple", "WARN")] == (1, 2)
    assert mapping[("apple", "WARN")] == (1, 4)
    assert mapping[("Ünicode Svc", "ERROR")] == (1, 0)
    assert mapping[("zeta", "INFO")] == (1, 1)
    assert mapping == expected_map(read_fixture("unicode.jsonl"))


def test_duplicate_records_all_counted(tmp_path):
    inp = copy_fixture("duplicates.jsonl", tmp_path)
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    assert_structure(rows)
    assert as_map(rows) == {("svc", "WARN"): (5, 12346)}


def test_empty_input_outputs_empty_array(tmp_path):
    inp = copy_fixture("empty.jsonl", tmp_path)
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    rows = load_output(str(out))
    assert rows == []


def test_input_file_preserved(tmp_path):
    inp = copy_fixture("basic.jsonl", tmp_path)
    with open(inp, "rb") as handle:
        before = handle.read()
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    with open(inp, "rb") as handle:
        after = handle.read()
    assert before == after


def test_unicode_fixture_input_preserved(tmp_path):
    inp = copy_fixture("unicode.jsonl", tmp_path)
    with open(inp, "rb") as handle:
        before = handle.read()
    out = tmp_path / "out.json"
    proc = run_cli(inp, str(out))
    assert proc.returncode == 0, proc.stderr
    with open(inp, "rb") as handle:
        after = handle.read()
    assert before == after


def test_different_inputs_produce_different_outputs(tmp_path):
    out1 = tmp_path / "o1.json"
    out2 = tmp_path / "o2.json"
    p1 = run_cli(copy_fixture("basic.jsonl", tmp_path), str(out1))
    assert p1.returncode == 0, p1.stderr
    p2 = run_cli(copy_fixture("duplicates.jsonl", tmp_path), str(out2))
    assert p2.returncode == 0, p2.stderr
    r1 = load_output(str(out1))
    r2 = load_output(str(out2))
    assert r1 != r2
    assert_structure(r1)
    assert_structure(r2)


def test_rerun_is_deterministic(tmp_path):
    inp = copy_fixture("unicode.jsonl", tmp_path)
    out1 = tmp_path / "o1.json"
    out2 = tmp_path / "o2.json"
    p1 = run_cli(inp, str(out1))
    assert p1.returncode == 0, p1.stderr
    p2 = run_cli(inp, str(out2))
    assert p2.returncode == 0, p2.stderr
    assert load_output(str(out1)) == load_output(str(out2))


def test_all_levels_and_large_nonnegative_values(tmp_path):
    records = [
        {"service": "s3", "level": "ERROR", "duration_ms": 0},
        {"service": "s1", "level": "INFO", "duration_ms": 999999999},
        {"service": "s1", "level": "ERROR", "duration_ms": 1},
        {"service": "s2", "level": "WARN", "duration_ms": 41},
        {"service": "s2", "level": "WARN", "duration_ms": 42},
        {"service": "s1", "level": "WARN", "duration_ms": 0},
    ]
    inp = tmp_path / "in.jsonl"
    with open(inp, "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")
    out = tmp_path / "out.json"
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    assert_structure(rows)
    assert as_map(rows) == expected_map(records)
    keys = [(r["service"], r["level"]) for r in rows]
    assert keys == sorted(keys)


def test_single_record_input(tmp_path):
    records = [{"service": "only", "level": "INFO", "duration_ms": 7}]
    inp = tmp_path / "one.jsonl"
    with open(inp, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(records[0]) + "\n")
    out = tmp_path / "out.json"
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    assert_structure(rows)
    assert rows == [
        {"service": "only", "level": "INFO", "count": 1, "total_duration_ms": 7}
    ]


def test_max_lines_boundary(tmp_path):
    records = []
    for i in range(1000):
        records.append(
            {
                "service": "svc%d" % (i % 7),
                "level": ("INFO", "WARN", "ERROR")[i % 3],
                "duration_ms": i,
            }
        )
    inp = tmp_path / "big.jsonl"
    with open(inp, "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")
    out = tmp_path / "out.json"
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0, proc.stderr
    rows = load_output(str(out))
    assert_structure(rows)
    assert as_map(rows) == expected_map(records)
    assert sum(r["count"] for r in rows) == 1000
    keys = [(r["service"], r["level"]) for r in rows]
    assert keys == sorted(keys)
