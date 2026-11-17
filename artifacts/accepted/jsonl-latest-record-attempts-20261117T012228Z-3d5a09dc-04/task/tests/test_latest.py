"""Behavioral tests for /app/latest.py (JSONL latest-per-key merge tool)."""

import json
import os
import subprocess
import sys

import pytest

APP = "/app/latest.py"
TIMEOUT = 10


def run_tool(tmp_path, events, raw_input=None, output_name="out.json"):
    """Write input fixture, run the CLI, return (input_text, output_path, proc)."""
    in_path = tmp_path / "events.jsonl"
    if raw_input is not None:
        in_path.write_text(raw_input, encoding="utf-8")
    else:
        in_path.write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
            encoding="utf-8",
        )
    in_before = in_path.read_bytes()
    out_path = tmp_path / output_name
    try:
        proc = subprocess.run(
            [sys.executable, APP, str(in_path), str(out_path)],
            capture_output=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("latest.py timed out after %ss" % TIMEOUT)
    assert in_path.read_bytes() == in_before, "input file was modified"
    return in_path, out_path, proc


def read_output(out_path, proc):
    assert proc.returncode == 0, "non-zero exit %r, stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    assert os.path.exists(out_path), "output file was not created"
    text = out_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        pytest.fail("output is not valid JSON: %r (%s)" % (text, exc))
    assert isinstance(data, list), "output must be a JSON array, got %r" % (data,)
    for rec in data:
        assert isinstance(rec, dict), "each array element must be an object"
        assert set(rec.keys()) == {"key", "version", "value"}, (
            "record must have exactly key/version/value, got %r" % (rec,)
        )
        assert isinstance(rec["key"], str)
        assert isinstance(rec["version"], int) and not isinstance(rec["version"], bool)
        assert isinstance(rec["value"], str)
    return data


def as_pairs(data):
    return [(r["key"], r["version"], r["value"]) for r in data]


def test_basic_example(tmp_path):
    events = [
        {"key": "db.url", "version": 3, "value": "postgres://a"},
        {"key": "cache.ttl", "version": 1, "value": "30"},
        {"key": "db.url", "version": 2, "value": "postgres://old"},
        {"key": "db.url", "version": 3, "value": "postgres://b"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [
        ("cache.ttl", 1, "30"),
        ("db.url", 3, "postgres://b"),
    ]


def test_structure_exact_fields(tmp_path):
    events = [
        {"key": "a", "version": 5, "value": "x"},
        {"key": "b", "version": 0, "value": ""},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)  # asserts exact keys and types
    assert len(data) == 2


def test_out_of_order_max_version_wins(tmp_path):
    events = [
        {"key": "k", "version": 10, "value": "v10"},
        {"key": "k", "version": 2, "value": "v2"},
        {"key": "k", "version": 7, "value": "v7"},
        {"key": "k", "version": 1, "value": "v1"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("k", 10, "v10")]


def test_older_version_after_newer_does_not_overwrite(tmp_path):
    events = [
        {"key": "k", "version": 4, "value": "new"},
        {"key": "k", "version": 3, "value": "old"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("k", 4, "new")]


def test_tie_on_max_version_takes_last(tmp_path):
    events = [
        {"key": "k", "version": 5, "value": "first"},
        {"key": "k", "version": 1, "value": "low"},
        {"key": "k", "version": 5, "value": "second"},
        {"key": "k", "version": 5, "value": "third"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("k", 5, "third")]


def test_tie_takes_last_even_if_not_adjacent(tmp_path):
    events = [
        {"key": "a", "version": 2, "value": "a-first"},
        {"key": "b", "version": 9, "value": "b"},
        {"key": "a", "version": 2, "value": "a-last"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("a", 2, "a-last"), ("b", 9, "b")]


def test_empty_input_produces_empty_array(tmp_path):
    in_path, out, proc = run_tool(tmp_path, [], raw_input="")
    assert in_path.read_bytes() == b""
    data = read_output(out, proc)
    assert data == []


def test_single_record(tmp_path):
    events = [{"key": "solo", "version": 0, "value": ""}]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("solo", 0, "")]


def test_zero_version_and_empty_value(tmp_path):
    events = [
        {"key": "z", "version": 0, "value": ""},
        {"key": "z", "version": 0, "value": "still-zero"},
        {"key": "a", "version": 0, "value": ""},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("a", 0, ""), ("z", 0, "still-zero")]


def test_unicode_keys_and_values(tmp_path):
    events = [
        {"key": "\u00e9clair", "version": 1, "value": "\u503c\u4e00"},
        {"key": "\u4e2d\u6587", "version": 2, "value": "caf\u00e9 \U0001f600"},
        {"key": "Zeta", "version": 1, "value": "ok"},
        {"key": "\u00e9clair", "version": 3, "value": "\u503c\u4e8c"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    result = {r["key"]: (r["version"], r["value"]) for r in data}
    assert result == {
        "Zeta": (1, "ok"),
        "\u4e2d\u6587": (2, "caf\u00e9 \U0001f600"),
        "\u00e9clair": (3, "\u503c\u4e8c"),
    }
    # unicode read back correctly means UTF-8 output was written
    assert out.read_text(encoding="utf-8").strip() != ""


def test_sorted_by_python_string_order(tmp_path):
    keys = ["b", "A", "a", "B", "aa", "aB", "1", "_", "z", "Z", "\u00e9", "e"]
    events = [{"key": k, "version": 1, "value": k} for k in keys]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert [r["key"] for r in data] == sorted(keys)


def test_no_duplicate_keys(tmp_path):
    events = []
    for i in range(30):
        events.append({"key": "k%d" % (i % 7), "version": i, "value": "v%d" % i})
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    keys = [r["key"] for r in data]
    assert len(keys) == len(set(keys)) == 7
    by_key = {r["key"]: r for r in data}
    for k, rec in by_key.items():
        idx = int(k[1:])
        best_version = max(i for i in range(30) if i % 7 == idx)
        assert rec["version"] == best_version
        assert rec["value"] == "v%d" % best_version


def test_thousand_lines(tmp_path):
    events = []
    for i in range(1000):
        # 100 keys, versions shuffled-ish
        key = "key%03d" % (i % 100)
        version = (i * 37) % 1000
        events.append({"key": key, "version": version, "value": "val%d" % i})
    # add an explicit max per a few keys at the end
    events.append({"key": "key000", "version": 2000, "value": "max"})
    events.append({"key": "key001", "version": 2000, "value": "max1"})
    events.append({"key": "key001", "version": 2000, "value": "max1-last"})
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    keys = [r["key"] for r in data]
    assert len(keys) == 100
    assert keys == sorted(keys)
    by_key = {r["key"]: r for r in data}
    assert by_key["key000"]["value"] == "max"
    assert by_key["key001"]["value"] == "max1-last"
    for k in keys:
        expected = max(
            e["version"] for e in events if e["key"] == k
        )
        assert by_key[k]["version"] == expected
        # last occurrence of that max version
        last = [e for e in events if e["key"] == k and e["version"] == expected][-1]
        assert by_key[k]["value"] == last["value"]


def test_large_version_values(tmp_path):
    events = [
        {"key": "k", "version": 2 ** 62, "value": "big"},
        {"key": "k", "version": 2 ** 62 - 1, "value": "smaller"},
        {"key": "k", "version": 2 ** 70 + 3, "value": "bigger"},
    ]
    _, out, proc = run_tool(tmp_path, events)
    data = read_output(out, proc)
    assert as_pairs(data) == [("k", 2 ** 70 + 3, "bigger")]


def test_input_preserved_during_run(tmp_path):
    # run_tool already asserts input is unchanged; this keeps an explicit check
    events = [{"key": "k", "version": 1, "value": "v"}]
    raw = json.dumps(events[0], ensure_ascii=False) + "\n"
    in_path, out, proc = run_tool(tmp_path, events, raw_input=raw)
    assert in_path.read_text(encoding="utf-8") == raw
    read_output(out, proc)


def test_output_only_std_lib_and_artifact(tmp_path):
    # artifact exists and runs with an isolated stdlib-only interpreter
    assert os.path.isfile(APP)
    events = [{"key": "k", "version": 1, "value": "v"}]
    in_path = tmp_path / "in.jsonl"
    in_path.write_text(json.dumps(events[0]) + "\n", encoding="utf-8")
    out_path = tmp_path / "out.json"
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PYTHONNOUSERSITE": "1",
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-S", APP, str(in_path), str(out_path)],
            capture_output=True,
            timeout=TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("latest.py timed out after %ss" % TIMEOUT)
    data = read_output(out_path, proc)
    assert as_pairs(data) == [("k", 1, "v")]
