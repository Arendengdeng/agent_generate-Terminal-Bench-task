"""Behavioral probe for the JSONL group-summary repair task."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
SCRIPT = os.path.join(APP, "summarize.py")

REQUIREMENTS = {"R1", "R2", "R3", "R4"}


def run_cli(input_path, output_path):
    return subprocess.run(
        [sys.executable, SCRIPT, input_path, output_path],
        cwd="/tmp",
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def write_jsonl(directory, name, records):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def text_of(completed):
    return completed.stdout.decode("utf-8", "replace") + completed.stderr.decode(
        "utf-8", "replace"
    )


def load_output(output_path):
    assert os.path.isfile(output_path), "output file was not created"
    with open(output_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        raise AssertionError("output is not valid JSON: %s" % exc)
    assert isinstance(data, list), "output JSON must be an array"
    return data


def run_case(directory, records, name):
    input_path = write_jsonl(directory, name + ".jsonl", records)
    output_path = os.path.join(directory, name + ".json")
    completed = run_cli(input_path, output_path)
    assert completed.returncode == 0, "non-zero exit: %s" % text_of(completed)
    return load_output(output_path)


def expected_rows(records):
    groups = {}
    for record in records:
        key = (record["service"], record["level"])
        count, total = groups.get(key, (0, 0))
        groups[key] = (count + 1, total + int(record["duration_ms"]))
    rows = [
        {
            "service": service,
            "level": level,
            "count": groups[(service, level)][0],
            "total_duration_ms": groups[(service, level)][1],
        }
        for service, level in sorted(groups)
    ]
    return rows


def assert_matches(rows, expected):
    assert rows == expected, "got %r expected %r" % (rows, expected)


def check_r1(directory):
    records = [
        {"service": "api", "level": "INFO", "duration_ms": 10},
        {"service": "api", "level": "ERROR", "duration_ms": 5},
        {"service": "web", "level": "WARN", "duration_ms": 0},
    ]
    input_path = write_jsonl(directory, "r1.jsonl", records)
    output_path = os.path.join(directory, "r1.json")
    completed = run_cli(input_path, output_path)
    assert completed.returncode == 0, "non-zero exit: %s" % text_of(completed)
    rows = load_output(output_path)
    assert len(rows) == 3, "expected 3 groups, got %d" % len(rows)
    for row in rows:
        assert isinstance(row, dict), "each row must be an object"
        assert set(row.keys()) == {
            "service",
            "level",
            "count",
            "total_duration_ms",
        }, "unexpected field set: %r" % sorted(row.keys())
        assert isinstance(row["count"], int) and not isinstance(row["count"], bool)
        assert isinstance(row["total_duration_ms"], int)
    assert_matches(rows, expected_rows(records))


def check_r2(directory):
    records = [
        {"service": "api", "level": "INFO", "duration_ms": 12},
        {"service": "api", "level": "INFO", "duration_ms": 12},
        {"service": "api", "level": "INFO", "duration_ms": 0},
        {"service": "api", "level": "ERROR", "duration_ms": 7},
        {"service": "api", "level": "INFO", "duration_ms": 100},
        {"service": "api", "level": "WARN", "duration_ms": 3},
        {"service": "api", "level": "ERROR", "duration_ms": 7},
        {"service": "web", "level": "INFO", "duration_ms": 0},
    ]
    rows = run_case(directory, records, "r2")
    assert_matches(rows, expected_rows(records))
    by_key = {(r["service"], r["level"]): r for r in rows}
    assert by_key[("api", "INFO")]["count"] == 4
    assert by_key[("api", "INFO")]["total_duration_ms"] == 124
    assert by_key[("api", "ERROR")]["count"] == 2
    assert by_key[("api", "ERROR")]["total_duration_ms"] == 14
    assert by_key[("web", "INFO")]["total_duration_ms"] == 0


def check_r3(directory):
    empty_path = write_jsonl(directory, "r3_empty.jsonl", [])
    out_path = os.path.join(directory, "r3_empty.json")
    completed = run_cli(empty_path, out_path)
    assert completed.returncode == 0, "non-zero exit on empty input: %s" % text_of(
        completed
    )
    assert load_output(out_path) == [], "empty input must produce []"

    records = [
        {"service": "订单服务", "level": "WARN", "duration_ms": 4},
        {"service": "web", "level": "ERROR", "duration_ms": 1},
        {"service": "web", "level": "INFO", "duration_ms": 2},
        {"service": "web", "level": "WARN", "duration_ms": 3},
        {"service": "订单服务", "level": "INFO", "duration_ms": 9},
        {"service": "auth", "level": "ERROR", "duration_ms": 8},
        {"service": "web", "level": "INFO", "duration_ms": 5},
        {"service": "api", "level": "WARN", "duration_ms": 6},
        {"service": "auth", "level": "INFO", "duration_ms": 11},
    ]
    rows = run_case(directory, records, "r3")
    assert_matches(rows, expected_rows(records))
    keys = [(r["service"], r["level"]) for r in rows]
    assert keys == sorted(keys), "rows are not sorted by service then level"
    # Alphabetical order in Python's string ordering is codepoint based.
    assert rows[0]["service"] == "api", "unexpected first service %r" % rows[0]["service"]
    assert rows[-1]["service"] == "订单服务"
    assert len({(r["service"], r["level"]) for r in rows}) == len(rows)
    assert_matches(rows, expected_rows(records))


def check_r4(directory):
    records = [
        {"service": "svc-%d" % (i % 7), "level": ["INFO", "WARN", "ERROR"][i % 3],
         "duration_ms": i}
        for i in range(1000)
    ]
    input_path = write_jsonl(directory, "r4.jsonl", records)
    before = hashlib.sha256(open(input_path, "rb").read()).hexdigest()
    output_path = os.path.join(directory, "r4.json")
    completed = run_cli(input_path, output_path)
    assert completed.returncode == 0, "non-zero exit: %s" % text_of(completed)
    rows = load_output(output_path)
    assert_matches(rows, expected_rows(records))
    after = hashlib.sha256(open(input_path, "rb").read()).hexdigest()
    assert before == after, "input file was modified"
    assert os.path.isfile(SCRIPT), "summarize.py missing"

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import ast,sys\n"
                "src=open('/app/summarize.py',encoding='utf-8').read()\n"
                "tree=ast.parse(src)\n"
                "mods=set()\n"
                "for n in ast.walk(tree):\n"
                "    if isinstance(n,ast.Import):\n"
                "        mods.update(a.name.split('.')[0] for a in n.names)\n"
                "    elif isinstance(n,ast.ImportFrom) and n.level==0 and n.module:\n"
                "        mods.add(n.module.split('.')[0])\n"
                "print(','.join(sorted(mods)))\n"
            ),
        ],
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )
    assert probe.returncode == 0, "could not inspect imports: %s" % text_of(probe)
    mods = [m for m in probe.stdout.decode().strip().split(",") if m]
    allowed = set(sys.stdlib_module_names)
    third_party = [m for m in mods if m not in allowed]
    assert not third_party, "non-stdlib imports: %r" % third_party


def check(requirement_id):
    if requirement_id not in REQUIREMENTS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    handler = {
        "R1": check_r1,
        "R2": check_r2,
        "R3": check_r3,
        "R4": check_r4,
    }[requirement_id]
    with tempfile.TemporaryDirectory(prefix="probe-", dir="/tmp") as directory:
        handler(directory)


if __name__ == "__main__":
    for rid in sorted(REQUIREMENTS):
        try:
            check(rid)
        except AssertionError as exc:
            print("FAIL %s: %s" % (rid, exc))
        else:
            print("PASS %s" % rid)
