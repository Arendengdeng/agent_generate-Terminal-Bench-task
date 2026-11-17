"""Black-box tests for /app/summarize.py (JSONL service aggregation CLI)."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path("/app")
SCRIPT = APP / "summarize.py"
FIXTURES = Path(__file__).parent / "fixtures"
REQUIRED_KEYS = {"service", "count", "total_duration_ms", "max_duration_ms"}


def run_cli(tmp_path, text=None, input_bytes=None, name="input.jsonl", extra_args=None):
    """Write fixture input, run the CLI, assert exit code and output, return (data, out)."""
    src = tmp_path / name
    if input_bytes is not None:
        src.write_bytes(input_bytes)
    else:
        src.write_text(text, encoding="utf-8")
    out = tmp_path / "output.json"
    argv = [sys.executable, str(SCRIPT), str(src), str(out)]
    if extra_args is not None:
        argv = [sys.executable, str(SCRIPT)] + extra_args
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, (
        f"CLI exited {proc.returncode}; stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert out.exists(), "CLI did not produce output file"
    raw = out.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        pytest.fail(f"output is not valid UTF-8 JSON: {exc}: {raw!r}")
    return data, out


def summarize(records, tmp_path):
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    return run_cli(tmp_path, text=text)


def rec(service, level, duration_ms):
    return {"service": service, "level": level, "duration_ms": duration_ms}


def agg(records):
    expected = {}
    for r in records:
        e = expected.get(r["service"])
        if e is None:
            expected[r["service"]] = {
                "service": r["service"],
                "count": 1,
                "total_duration_ms": r["duration_ms"],
                "max_duration_ms": r["duration_ms"],
            }
        else:
            e["count"] += 1
            e["total_duration_ms"] += r["duration_ms"]
            e["max_duration_ms"] = max(e["max_duration_ms"], r["duration_ms"])
    return [expected[k] for k in sorted(expected)]


def by_service(data):
    assert isinstance(data, list), f"expected JSON array, got {type(data)}: {data!r}"
    result = {}
    for obj in data:
        assert isinstance(obj, dict), f"array element not an object: {obj!r}"
        assert "service" in obj
        assert obj["service"] not in result, f"duplicate service entry: {obj['service']!r}"
        result[obj["service"]] = obj
    return result


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse_fixture_records(name):
    return [json.loads(line) for line in load_fixture(name).splitlines() if line.strip()]


# ---------------------------------------------------------------- R1


def test_r1_instruction_sample(tmp_path):
    data, _ = summarize(
        [
            rec("beta", "INFO", 5),
            rec("alpha", "ERROR", 7),
            rec("beta", "ERROR", 9),
            rec("beta", "INFO", 9),
        ],
        tmp_path,
    )
    assert data == [
        {"service": "alpha", "count": 1, "total_duration_ms": 7, "max_duration_ms": 7},
        {"service": "beta", "count": 3, "total_duration_ms": 23, "max_duration_ms": 9},
    ]


def test_r1_output_exact_keys_and_integer_types(tmp_path):
    data, _ = summarize(
        [rec("svc", "INFO", 3), rec("svc", "WARN", 4), rec("svc", "ERROR", 0)],
        tmp_path,
    )
    assert isinstance(data, list) and len(data) == 1
    obj = data[0]
    assert set(obj.keys()) == REQUIRED_KEYS, f"unexpected key set: {sorted(obj.keys())}"
    assert isinstance(obj["count"], int) and not isinstance(obj["count"], bool)
    assert isinstance(obj["total_duration_ms"], int) and not isinstance(
        obj["total_duration_ms"], bool
    )
    assert isinstance(obj["max_duration_ms"], int) and not isinstance(
        obj["max_duration_ms"], bool
    )
    assert obj == {
        "service": "svc",
        "count": 3,
        "total_duration_ms": 7,
        "max_duration_ms": 4,
    }


def test_r1_output_parses_as_utf8_json(tmp_path):
    data, out = run_cli(tmp_path, text=load_fixture("unicode.jsonl"))
    text = out.read_bytes().decode("utf-8")
    assert json.loads(text) == data
    assert [o["service"] for o in data] == ["Zebra", "alpha", "服务-乙", "日本"]


def test_r1_accepts_output_path_in_nested_relative_location(tmp_path):
    (tmp_path / "sub").mkdir()
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps(rec("api", "INFO", 5)) + "\n", encoding="utf-8")
    out = tmp_path / "sub" / "report.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"service": "api", "count": 1, "total_duration_ms": 5, "max_duration_ms": 5}
    ]


# ---------------------------------------------------------------- R2


def test_r2_grouping_across_levels(tmp_path):
    data, _ = summarize(
        [
            rec("a", "INFO", 1),
            rec("a", "WARN", 10),
            rec("a", "ERROR", 100),
            rec("b", "WARN", 2),
            rec("b", "ERROR", 2),
        ],
        tmp_path,
    )
    got = by_service(data)
    assert got["a"] == {
        "service": "a",
        "count": 3,
        "total_duration_ms": 111,
        "max_duration_ms": 100,
    }
    assert got["b"] == {
        "service": "b",
        "count": 2,
        "total_duration_ms": 4,
        "max_duration_ms": 2,
    }


def test_r2_identical_duplicate_records_counted(tmp_path):
    r = rec("dup", "INFO", 7)
    data, _ = summarize([r, r, r, r], tmp_path)
    assert data == [
        {"service": "dup", "count": 4, "total_duration_ms": 28, "max_duration_ms": 7}
    ]


def test_r2_max_is_maximum_not_last_nor_sum(tmp_path):
    data, _ = summarize(
        [rec("m", "INFO", 5), rec("m", "WARN", 1), rec("m", "ERROR", 3)],
        tmp_path,
    )
    assert data == [
        {"service": "m", "count": 3, "total_duration_ms": 9, "max_duration_ms": 5}
    ]


def test_r2_group_by_service_not_level(tmp_path):
    data, _ = summarize(
        [rec("s1", "INFO", 1), rec("s2", "INFO", 2), rec("s1", "INFO", 3)],
        tmp_path,
    )
    assert [o["service"] for o in data] == ["s1", "s2"]
    got = by_service(data)
    assert got["s1"] == {
        "service": "s1",
        "count": 2,
        "total_duration_ms": 4,
        "max_duration_ms": 3,
    }
    assert got["s2"] == {
        "service": "s2",
        "count": 1,
        "total_duration_ms": 2,
        "max_duration_ms": 2,
    }


def test_r2_zero_durations(tmp_path):
    data, _ = summarize(
        [rec("z", "INFO", 0), rec("z", "ERROR", 0), rec("y", "WARN", 0)],
        tmp_path,
    )
    got = by_service(data)
    assert got["z"] == {
        "service": "z",
        "count": 2,
        "total_duration_ms": 0,
        "max_duration_ms": 0,
    }
    assert got["y"] == {
        "service": "y",
        "count": 1,
        "total_duration_ms": 0,
        "max_duration_ms": 0,
    }


def test_r2_mixed_fixture_matches_independent_aggregation(tmp_path):
    records = parse_fixture_records("mixed.jsonl")
    data, _ = run_cli(tmp_path, text=load_fixture("mixed.jsonl"))
    assert data == agg(records)
    got = by_service(data)
    assert got["api"]["count"] == 5
    assert got["api"]["total_duration_ms"] == 57
    assert got["api"]["max_duration_ms"] == 30
    assert got["db"]["total_duration_ms"] == 87
    assert got["db"]["max_duration_ms"] == 40


def test_r2_maximum_input_size_1000_lines(tmp_path):
    records = []
    services = ["api", "db", "cache", "worker", "gateway"]
    levels = ["INFO", "WARN", "ERROR"]
    for i in range(1000):
        records.append(
            rec(services[(i * 7) % len(services)], levels[i % 3], (i * 37) % 997)
        )
    data, _ = summarize(records, tmp_path)
    assert data == agg(records)


def test_r2_large_durations_exact(tmp_path):
    big = 10 ** 15
    data, _ = summarize(
        [rec("big", "INFO", big), rec("big", "ERROR", big), rec("big", "WARN", 1)],
        tmp_path,
    )
    assert data == [
        {
            "service": "big",
            "count": 3,
            "total_duration_ms": 2 * big + 1,
            "max_duration_ms": big,
        }
    ]


# ---------------------------------------------------------------- R3


def test_r3_sorted_ascending_python_string_order(tmp_path):
    services = [
        "b",
        "a",
        "B",
        "A",
        "z",
        "Z",
        "é",
        "服务-乙",
        "服务-甲",
        "日本",
        "a\u0300",
        "_x",
        "1num",
    ]
    records = [rec(s, "INFO", i) for i, s in enumerate(services)]
    data, _ = summarize(records, tmp_path)
    got_services = [o["service"] for o in data]
    assert got_services == sorted(services)
    assert set(got_services) == set(services)
    assert len(got_services) == len(services)


def test_r3_only_present_groups(tmp_path):
    data, _ = summarize([rec("only", "WARN", 3)], tmp_path)
    assert data == [
        {"service": "only", "count": 1, "total_duration_ms": 3, "max_duration_ms": 3}
    ]


def test_r3_empty_file_returns_empty_array(tmp_path):
    data, out = run_cli(tmp_path, text="")
    assert data == []
    assert json.loads(out.read_text(encoding="utf-8")) == []


def test_r3_unicode_fixture_grouping_and_order(tmp_path):
    data, _ = run_cli(tmp_path, text=load_fixture("unicode.jsonl"))
    assert [o["service"] for o in data] == ["Zebra", "alpha", "服务-乙", "日本"]
    got = by_service(data)
    assert got["服务-乙"] == {
        "service": "服务-乙",
        "count": 2,
        "total_duration_ms": 12,
        "max_duration_ms": 10,
    }
    assert got["日本"] == {
        "service": "日本",
        "count": 1,
        "total_duration_ms": 1,
        "max_duration_ms": 1,
    }
    assert got["Zebra"] == {
        "service": "Zebra",
        "count": 1,
        "total_duration_ms": 4,
        "max_duration_ms": 4,
    }
    assert got["alpha"] == {
        "service": "alpha",
        "count": 2,
        "total_duration_ms": 5,
        "max_duration_ms": 3,
    }


def test_r3_repeat_runs_identical_output(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(load_fixture("mixed.jsonl"), encoding="utf-8")
    outs = []
    for i in range(2):
        out = tmp_path / f"out{i}.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(src), str(out)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(json.loads(out.read_text(encoding="utf-8")))
    assert outs[0] == outs[1]


def test_r3_input_without_trailing_newline(tmp_path):
    text = json.dumps(rec("noeol", "INFO", 2)) + "\n" + json.dumps(
        rec("noeol", "WARN", 5)
    )
    data, _ = run_cli(tmp_path, text=text)
    assert data == [
        {"service": "noeol", "count": 2, "total_duration_ms": 7, "max_duration_ms": 5}
    ]


def test_r3_single_line_input(tmp_path):
    data, _ = run_cli(tmp_path, text=json.dumps(rec("solo", "ERROR", 42)) + "\n")
    assert data == [
        {"service": "solo", "count": 1, "total_duration_ms": 42, "max_duration_ms": 42}
    ]


# ---------------------------------------------------------------- R4


def test_r4_input_file_unmodified(tmp_path):
    payload = load_fixture("mixed.jsonl").encode("utf-8")
    src = tmp_path / "keep.jsonl"
    src.write_bytes(payload)
    before_hash = hashlib.sha256(payload).hexdigest()
    before_stat = src.stat()
    out = tmp_path / "res.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert src.read_bytes() == payload
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before_hash
    assert src.stat().st_size == before_stat.st_size
    assert src.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_r4_input_bytes_crlf_and_utf8(tmp_path):
    payload = load_fixture("unicode.jsonl").replace("\n", "\r\n").encode("utf-8")
    src = tmp_path / "crlf.jsonl"
    src.write_bytes(payload)
    out = tmp_path / "o.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [o["service"] for o in data] == ["Zebra", "alpha", "服务-乙", "日本"]
    assert src.read_bytes() == payload


def test_r4_runs_without_site_packages(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps(rec("api", "INFO", 5)) + "\n", encoding="utf-8")
    out = tmp_path / "out.json"
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, "-S", "-I", str(SCRIPT), str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd="/",
        env=env,
    )
    assert proc.returncode == 0, (
        f"CLI failed without site-packages (non-stdlib dependency?): {proc.stderr}"
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [
        {"service": "api", "count": 1, "total_duration_ms": 5, "max_duration_ms": 5}
    ]


def test_r4_no_extra_deliverable_files_in_app(tmp_path):
    assert SCRIPT.is_file(), "missing /app/summarize.py"
    extra = sorted(
        p.name for p in APP.iterdir() if p.name not in {"summarize.py", "__pycache__"}
    )
    assert extra == [], f"unexpected additional deliverable files in /app: {extra}"
