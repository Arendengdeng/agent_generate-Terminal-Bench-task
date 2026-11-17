"""Behavioural probe for the customer CSV cleaning CLI."""

import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

APP_DIR = "/app"
CLEAN_PY = os.path.join(APP_DIR, "clean.py")
COMMAND_TIMEOUT_SEC = 10

REQUIREMENT_IDS = {"R1", "R2", "R3", "R4"}


def _run(in_path, out_path):
    return subprocess.run(
        [sys.executable, CLEAN_PY, in_path, out_path],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _parse_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        content = fh.read()
    rows = list(csv.reader(io.StringIO(content)))
    # Drop a single trailing empty line produced by a final newline.
    if rows and rows[-1] == []:
        rows.pop()
    return rows


def _make_fixture(dir_path, name, text):
    path = os.path.join(dir_path, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def _clean(in_text, expect_rows):
    """Run the CLI on in_text and assert the output rows match."""
    tmp = tempfile.mkdtemp(prefix="custclean-", dir="/tmp")
    try:
        in_path = _make_fixture(tmp, "in.csv", in_text)
        out_path = os.path.join(tmp, "out.csv")
        with open(in_path, "rb") as fh:
            before = fh.read()
        proc = _run(in_path, out_path)
        assert proc.returncode == 0, (
            "exit code %r, stderr=%r" % (proc.returncode, proc.stderr)
        )
        assert os.path.isfile(out_path), "output file missing"
        rows = _parse_csv(out_path)
        assert rows == expect_rows, "output %r != expected %r" % (rows, expect_rows)
        with open(in_path, "rb") as fh:
            after = fh.read()
        assert before == after, "input file was modified"
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_r1():
    tmp = tempfile.mkdtemp(prefix="custclean-", dir="/tmp")
    try:
        in_path = _make_fixture(
            tmp,
            "in.csv",
            "email,name\nalpha@example.com,Alpha One\n",
        )
        out_path = os.path.join(tmp, "custom_out.csv")
        proc = subprocess.run(
            [sys.executable, CLEAN_PY, in_path, out_path],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
        )
        assert proc.returncode == 0, (
            "exit code %r, stderr=%r" % (proc.returncode, proc.stderr)
        )
        assert os.path.isfile(out_path), "output file not created at given path"
        rows = _parse_csv(out_path)
        assert rows == [["email", "name"], ["alpha@example.com", "Alpha One"]], (
            "unexpected output %r" % (rows,)
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_r2():
    _clean(
        "email,name\n"
        "  Alice.Wang@Example.COM , Alice Wang\n"
        "bob@example.com,Bob Lee\n"
        "carol@example.com,\"Lee, Carol\"\n"
        "Alice.wang@example.com,Alicia Wang\n"
        "dave@example.com,  Dave Diaz\n"
        "bob@example.com ,Bobby Lee\n"
        "ALICE.WANG@example.com,\"Wang,  Alice\"\n"
        "eve@example.com,Eve \"E\" Adams\n",
        [
            ["email", "name"],
            ["alice.wang@example.com", "Alice Wang"],
            ["bob@example.com", "Bob Lee"],
            ["carol@example.com", "Lee, Carol"],
            ["dave@example.com", "Dave Diaz"],
            ["eve@example.com", 'Eve "E" Adams'],
        ],
    )
    # Name case must be preserved; only edge whitespace is trimmed.
    _clean(
        "email,name\nmike@example.com,\"  Mike O'Neil, Jr.  \"\nmike@example.com,Other\n",
        [["email", "name"], ["mike@example.com", "Mike O'Neil, Jr."]],
    )


def _check_r3():
    # Header-only input.
    _clean("email,name\n", [["email", "name"]])
    _clean("email,name", [["email", "name"]])
    # Unrelated small legal input, order of first appearance with mixed case.
    _clean(
        "email,name\n"
        "Z@example.com,Zed\n"
        "a@example.com,Ay\n"
        "y@example.com,\"Y, Why\"\n"
        "z@EXAMPLE.com,Zed Again\n",
        [
            ["email", "name"],
            ["z@example.com", "Zed"],
            ["a@example.com", "Ay"],
            ["y@example.com", "Y, Why"],
        ],
    )
    # Larger legal fixture (boundary-ish) with many duplicates.
    lines = ["email,name"]
    for i in range(500):
        lines.append("User%d@Example.com,User %d" % (i, i))
    for i in range(500):
        lines.append(" user%d@example.COM ,Duplicate %d" % (i, i))
    expected = [["email", "name"]]
    for i in range(500):
        expected.append(["user%d@example.com" % i, "User %d" % i])
    _clean("\n".join(lines) + "\n", expected)
    # Embedded newline inside a quoted name is valid CSV.
    _clean(
        'email,name\nmulti@example.com,"Line One\nLine Two"\n',
        [["email", "name"], ["multi@example.com", "Line One\nLine Two"]],
    )


def _check_r4():
    tmp = tempfile.mkdtemp(prefix="custclean-", dir="/tmp")
    try:
        in_path = _make_fixture(
            tmp,
            "in.csv",
            "email,name\nKeep@Example.com,Keep Me\nkeep@example.com,Second\n",
        )
        out_path = os.path.join(tmp, "out.csv")
        with open(in_path, "rb") as fh:
            before = fh.read()
        before_stat = os.stat(in_path)

        # Run with a sanitised environment: only stdlib must be needed.
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "PYTHONPATH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        proc = subprocess.run(
            [sys.executable, CLEAN_PY, in_path, out_path],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            env=env,
        )
        assert proc.returncode == 0, (
            "exit code %r, stderr=%r" % (proc.returncode, proc.stderr)
        )
        with open(in_path, "rb") as fh:
            after = fh.read()
        after_stat = os.stat(in_path)
        assert before == after, "input file content changed"
        assert before_stat.st_mtime == after_stat.st_mtime, "input file mtime changed"
        assert before_stat.st_size == after_stat.st_size, "input file size changed"
        rows = _parse_csv(out_path)
        assert rows == [
            ["email", "name"],
            ["keep@example.com", "Keep Me"],
        ], "unexpected output %r" % (rows,)

        # Running twice on the same input must not corrupt the input either.
        proc2 = _run(in_path, out_path)
        assert proc2.returncode == 0, "second run failed: %r" % (proc2.stderr,)
        with open(in_path, "rb") as fh:
            assert fh.read() == before, "input file content changed on second run"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_CHECKS = {
    "R1": _check_r1,
    "R2": _check_r2,
    "R3": _check_r3,
    "R4": _check_r4,
}


def check(requirement_id):
    if requirement_id not in _CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    _CHECKS[requirement_id]()
