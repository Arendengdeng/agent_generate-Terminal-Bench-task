"""Behavioral tests for /app/summarize.py (JSONL service aggregation CLI)."""

import json
import os
import subprocess
import sys

import pytest

APP_DIR = "/app"
SCRIPT = os.path.join(APP_DIR, "summarize.py")
TIMEOUT = 10

FIELDS = {"service", "count", "total_duration_ms", "max_duration_ms"}


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_cli(input_path, output_path):
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(input_path), str(output_path)],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
    )
    return proc


def load_report(input_path, output_path):
    proc = run_cli(input_path, output_path)
    assert proc.returncode == 0, (
        "CLI failed: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
    )
    assert os.path.isfile(str(output_path)), "output file was not created"
    with open(str(output_path), "r", encoding="utf-8") as handle:
        text = handle.read()
    try:
        data = json.loads(text)
    except ValueError as exc:
        pytest.fail("output is not valid JSON: %s (%r)" % (exc, text[:500]))
    return data


def expected_report(records):
    agg = {}
    for record in records:
        service = record["service"]
        duration = record["duration_ms"]
        entry = agg.setdefault(
            service, {"service": service, "count": 0, "total_duration_ms": 0,
                      "max_duration_ms": duration}
        )
        entry["count"] += 1
        entry["total_duration_ms"] += duration
        if duration > entry["max_duration_ms"]:
            entry["max_duration_ms"] = duration
    return [agg[s] for s in sorted(agg)]


def assert_valid_structure(data, records):
    assert isinstance(data, list), "report must be a JSON array"
    services = sorted({record["service"] for record in records})
    assert [obj["service"] for obj in data] == services, (
        "report services mismatch: %r vs %r" % ([o.get("service") for o in data], services)
    )
    for obj in data:
        assert isinstance(obj, dict)
        assert set(obj.keys()) == FIELDS, "unexpected fields: %r" % (sorted(obj.keys()),)
        assert isinstance(obj["service"], str)
        assert isinstance(obj["count"], int) and not isinstance(obj["count"], bool)
        assert isinstance(obj["total_duration_ms"], int) and not isinstance(
            obj["total_duration_ms"], bool)
        assert isinstance(obj["max_duration_ms"], int) and not isinstance(
            obj["max_duration_ms"], bool)


def test_sample_exit_code_and_structure(tmp_path):
    records = [
        {"service": "beta", "level": "INFO", "duration_ms": 5},
        {"service": "alpha", "level": "ERROR", "duration_ms": 7},
        {"service": "beta", "level": "ERROR", "duration_ms": 9},
        {"service": "beta", "level": "INFO", "duration_ms": 9},
    ]
    inp = tmp_path / "sample.jsonl"
    out = tmp_path / "sample.json"
    write_jsonl(str(inp), records)
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    assert os.path.isfile(str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert_valid_structure(data, records)


def test_sample_values_exact(tmp_path):
    records = [
        {"service": "beta", "level": "INFO", "duration_ms": 5},
        {"service": "alpha", "level": "ERROR", "duration_ms": 7},
        {"service": "beta", "level": "ERROR", "duration_ms": 9},
        {"service": "beta", "level": "INFO", "duration_ms": 9},
    ]
    inp = tmp_path / "sample.jsonl"
    out = tmp_path / "sample.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert data == [
        {"service": "alpha", "count": 1, "total_duration_ms": 7, "max_duration_ms": 7},
        {"service": "beta", "count": 3, "total_duration_ms": 23, "max_duration_ms": 9},
    ]


def test_groups_only_by_service_across_levels(tmp_path):
    records = [
        {"service": "svc", "level": "INFO", "duration_ms": 1},
        {"service": "svc", "level": "WARN", "duration_ms": 10},
        {"service": "svc", "level": "ERROR", "duration_ms": 100},
        {"service": "svc", "level": "INFO", "duration_ms": 2},
        {"service": "other", "level": "INFO", "duration_ms": 0},
    ]
    inp = tmp_path / "levels.jsonl"
    out = tmp_path / "levels.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert_valid_structure(data, records)
    assert data == expected_report(records)
    assert data[0]["service"] == "other"
    assert data[1] == {"service": "svc", "count": 4, "total_duration_ms": 113,
                       "max_duration_ms": 100}


def test_duplicate_records_not_lost(tmp_path):
    rec = {"service": "dup", "level": "INFO", "duration_ms": 4}
    records = [dict(rec) for _ in range(7)] + [
        {"service": "dup", "level": "INFO", "duration_ms": 6},
        {"service": "dup", "level": "INFO", "duration_ms": 4},
    ]
    inp = tmp_path / "dups.jsonl"
    out = tmp_path / "dups.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert data == [{"service": "dup", "count": 9, "total_duration_ms": 38,
                     "max_duration_ms": 6}]


def test_max_across_levels_not_per_level(tmp_path):
    records = [
        {"service": "m", "level": "INFO", "duration_ms": 50},
        {"service": "m", "level": "ERROR", "duration_ms": 1},
        {"service": "m", "level": "WARN", "duration_ms": 50},
        {"service": "n", "level": "INFO", "duration_ms": 0},
        {"service": "n", "level": "INFO", "duration_ms": 0},
    ]
    inp = tmp_path / "max.jsonl"
    out = tmp_path / "max.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert_valid_structure(data, records)
    assert data == [
        {"service": "m", "count": 3, "total_duration_ms": 101, "max_duration_ms": 50},
        {"service": "n", "count": 2, "total_duration_ms": 0, "max_duration_ms": 0},
    ]


def test_empty_input_outputs_empty_array(tmp_path):
    inp = tmp_path / "empty.jsonl"
    out = tmp_path / "empty.json"
    inp.write_bytes(b"")
    data = load_report(str(inp), str(out))
    assert data == []


def test_empty_input_output_file_is_valid_json(tmp_path):
    inp = tmp_path / "empty2.jsonl"
    out = tmp_path / "empty2.json"
    inp.write_bytes(b"")
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0
    assert os.path.isfile(str(out))
    text = out.read_text(encoding="utf-8")
    assert json.loads(text) == []


def test_ordering_python_string_sorted(tmp_path):
    names = ["zeta", "Alpha", "alpha", "beta", "Zeta", "a", "A", "10", "2", "_u"]
    records = [
        {"service": name, "level": "INFO", "duration_ms": i}
        for i, name in enumerate(names)
    ]
    inp = tmp_path / "order.jsonl"
    out = tmp_path / "order.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert_valid_structure(data, records)
    expected = sorted(names)
    assert [obj["service"] for obj in data] == expected
    for obj in data:
        assert obj["count"] == 1
        assert obj["total_duration_ms"] == obj["max_duration_ms"]


def test_unicode_service_names_sorted(tmp_path):
    names = ["服务-乙", "服务-甲", "service", "Ñandú", "日本語", "ASCII", "é", "Z", "😀"]
    records = []
    for name in names:
        records.append({"service": name, "level": "WARN", "duration_ms": 3})
        records.append({"service": name, "level": "INFO", "duration_ms": 11})
    records.append({"service": "服务-甲", "level": "ERROR", "duration_ms": 30})
    inp = tmp_path / "unicode.jsonl"
    out = tmp_path / "unicode.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert_valid_structure(data, records)
    expected_order = sorted({r["service"] for r in records})
    assert [obj["service"] for obj in data] == expected_order
    by_name = {obj["service"]: obj for obj in data}
    assert by_name["服务-甲"] == {"service": "服务-甲", "count": 3,
                                 "total_duration_ms": 55, "max_duration_ms": 30}
    assert by_name["日本語"] == {"service": "日本語", "count": 2,
                                "total_duration_ms": 14, "max_duration_ms": 11}


def test_unicode_output_encoded_utf8_readable(tmp_path):
    records = [{"service": "服务-乙", "level": "INFO", "duration_ms": 1}]
    inp = tmp_path / "u8.jsonl"
    out = tmp_path / "u8.json"
    write_jsonl(str(inp), records)
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0
    raw = out.read_bytes()
    raw.decode("utf-8")
    data = json.loads(raw.decode("utf-8"))
    assert data == [{"service": "服务-乙", "count": 1,
                     "total_duration_ms": 1, "max_duration_ms": 1}]


def test_input_file_not_modified(tmp_path):
    records = [
        {"service": "b", "level": "ERROR", "duration_ms": 5},
        {"service": "a", "level": "INFO", "duration_ms": 1},
        {"service": "b", "level": "WARN", "duration_ms": 2},
    ]
    inp = tmp_path / "keep.jsonl"
    out = tmp_path / "keep.json"
    write_jsonl(str(inp), records)
    before_bytes = inp.read_bytes()
    before_stat = os.stat(str(inp))
    data = load_report(str(inp), str(out))
    assert data == expected_report(records)
    assert inp.read_bytes() == before_bytes, "input file content changed"
    after_stat = os.stat(str(inp))
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


def test_input_without_trailing_newline(tmp_path):
    inp = tmp_path / "nonl.jsonl"
    out = tmp_path / "nonl.json"
    lines = [
        {"service": "x", "level": "INFO", "duration_ms": 2},
        {"service": "y", "level": "INFO", "duration_ms": 3},
    ]
    text = "\n".join(json.dumps(line) for line in lines)
    inp.write_text(text, encoding="utf-8")
    data = load_report(str(inp), str(out))
    assert data == [
        {"service": "x", "count": 1, "total_duration_ms": 2, "max_duration_ms": 2},
        {"service": "y", "count": 1, "total_duration_ms": 3, "max_duration_ms": 3},
    ]


def test_single_line_zero_duration(tmp_path):
    records = [{"service": "solo", "level": "INFO", "duration_ms": 0}]
    inp = tmp_path / "solo.jsonl"
    out = tmp_path / "solo.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert data == [{"service": "solo", "count": 1, "total_duration_ms": 0,
                     "max_duration_ms": 0}]


def test_large_input_1000_lines(tmp_path):
    records = []
    for i in range(1000):
        service = "svc-%02d" % (i % 37)
        level = ("INFO", "WARN", "ERROR")[i % 3]
        records.append({"service": service, "level": level, "duration_ms": i})
    inp = tmp_path / "big.jsonl"
    out = tmp_path / "big.json"
    write_jsonl(str(inp), records)
    proc = run_cli(str(inp), str(out))
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == expected_report(records)
    assert sum(obj["count"] for obj in data) == 1000


def test_extra_fields_ignored(tmp_path):
    records = [
        {"service": "e1", "level": "INFO", "duration_ms": 4, "note": "x", "host": "h1"},
        {"service": "e1", "level": "ERROR", "duration_ms": 6},
    ]
    inp = tmp_path / "extra.jsonl"
    out = tmp_path / "extra.json"
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert data == [{"service": "e1", "count": 2, "total_duration_ms": 10,
                     "max_duration_ms": 6}]


def test_output_path_relative_to_cwd_not_required_but_absolute_works(tmp_path):
    records = [
        {"service": "p", "level": "INFO", "duration_ms": 1},
        {"service": "q", "level": "INFO", "duration_ms": 2},
    ]
    inp = tmp_path / "paths.jsonl"
    out = tmp_path / "nested" / "paths.json"
    out.parent.mkdir()
    write_jsonl(str(inp), records)
    data = load_report(str(inp), str(out))
    assert data == expected_report(records)


def test_runtime_uses_only_stdlib(tmp_path):
    records = [{"service": "lib", "level": "INFO", "duration_ms": 1}]
    inp = tmp_path / "lib.jsonl"
    out = tmp_path / "lib.json"
    write_jsonl(str(inp), records)
    env = dict(os.environ)
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        [sys.executable, "-S", SCRIPT, str(inp), str(out)],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
        env=env,
    )
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"service": "lib", "count": 1, "total_duration_ms": 1,
                     "max_duration_ms": 1}]
