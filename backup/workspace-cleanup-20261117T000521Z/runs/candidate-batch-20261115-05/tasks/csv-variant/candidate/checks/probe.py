# -*- coding: utf-8 -*-
"""Self-check probe for the customer-list cleaning CLI.

Each ``check`` call exercises the CLI documented in the task contract:
``python /app/clean.py <input.csv> <output.csv>``.
"""

import csv
import os
import shutil
import subprocess
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP_DIR = "/app"
APP = os.path.join(APP_DIR, "clean.py")

REQUIREMENTS = ("R1", "R2", "R3", "R4")


def _write_input(tmpdir, content, name="input.csv"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return path


def _run(in_path, out_path):
    proc = subprocess.run(
        ["python", APP, in_path, out_path],
        cwd=tmpdir_cwd(),
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )
    return proc


def tmpdir_cwd():
    # /app is the documented working directory; never write there.
    return APP_DIR if os.path.isdir(APP_DIR) else "/tmp"


def _read_output(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return [row for row in csv.reader(fh)]


def _run_case(input_text):
    """Run the CLI on ``input_text`` and return (proc, output_rows, input_path, out_path)."""
    tmpdir = tempfile.mkdtemp(prefix="cleanprobe-", dir="/tmp")
    try:
        in_path = _write_input(tmpdir, input_text)
        out_path = os.path.join(tmpdir, "output.csv")
        proc = _run(in_path, out_path)
        rows = _read_output(out_path) if os.path.exists(out_path) else None
        return proc, rows, in_path, out_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _expect_ok(proc, rows):
    assert proc.returncode == 0, (
        "expected exit code 0, got %r (stderr=%r)" % (proc.returncode, proc.stderr)
    )
    assert rows is not None, "output file was not written"
    assert rows, "output CSV is empty"


def _check_r1():
    proc, rows, _in, _out = _run_case(
        "email,name\nx@example.com,X\n"
    )
    _expect_ok(proc, rows)
    assert rows[0] == ["email", "name"], "unexpected header: %r" % (rows[0],)


def _check_r2():
    text = (
        "email,name\n"
        " Alice@Example.com , Alice Smith\n"
        "bob@example.com,\"Bob, Jr.\"\n"
        "\"alice@example.com\",\"Alice S. (updated)\"\n"
        "carol@example.com,Carol\n"
        " bob@example.com ,\"Bob Jones\"\n"
    )
    proc, rows, _in, _out = _run_case(text)
    _expect_ok(proc, rows)
    expected = [
        ["email", "name"],
        ["alice@example.com", "Alice S. (updated)"],
        ["bob@example.com", "Bob Jones"],
        ["carol@example.com", "Carol"],
    ]
    assert rows == expected, "got %r expected %r" % (rows, expected)


def _check_r2_whitespace_and_quotes():
    # Tabs / leading & trailing spaces around email, commas + quotes in names.
    text = (
        "email,name\n"
        "\tFoo@Bar.COM  ,\"  Foo, the First  \"\n"
        "zed@example.com,\"Zed \"\"Z\"\" Zulu\"\n"
        "foo@bar.com  ,Foo Last\n"
    )
    proc, rows, _in, _out = _run_case(text)
    _expect_ok(proc, rows)
    expected = [
        ["email", "name"],
        ["foo@bar.com", "Foo Last"],
        ["zed@example.com", "Zed \"Z\" Zulu"],
    ]
    assert rows == expected, "got %r expected %r" % (rows, expected)


def _check_r3_header_only():
    for text in ("email,name\n", "email,name"):
        proc, rows, _in, _out = _run_case(text)
        assert proc.returncode == 0, "header-only input failed: %r" % (proc.stderr,)
        assert rows == [["email", "name"]], "got %r" % (rows,)


def _check_r3_varied():
    # Different legal input: unicode names preserved, mixed case emails, order
    # driven by first appearance not alphabet, single row.
    text = (
        "email,name\n"
        "Zoe@Mail.COM,Zoë Ünïcode\n"
        "amy@mail.com,Amy\n"
        "AMY@mail.com , Amy Two\n"
        "zoe@mail.com,Zoe Last\n"
        "amy@mail.com,Amy Three\n"
    )
    proc, rows, _in, _out = _run_case(text)
    _expect_ok(proc, rows)
    expected = [
        ["email", "name"],
        ["zoe@mail.com", "Zoe Last"],
        ["amy@mail.com", "Amy Three"],
    ]
    assert rows == expected, "got %r expected %r" % (rows, expected)

    proc, rows, _in, _out = _run_case("email,name\nonly@one.com,Only\n")
    _expect_ok(proc, rows)
    assert rows == [["email", "name"], ["only@one.com", "Only"]], "got %r" % (rows,)


def _check_r4_input_preserved():
    tmpdir = tempfile.mkdtemp(prefix="cleanprobe-r4-", dir="/tmp")
    try:
        text = "email,name\n A@B.com ,A\n a@b.com ,A2\n"
        in_path = _write_input(tmpdir, text)
        with open(in_path, "rb") as fh:
            before = fh.read()
        with open(in_path, "rb") as fh:
            st_before = os.stat(in_path)
        out_path = os.path.join(tmpdir, "out.csv")
        proc = _run(in_path, out_path)
        assert proc.returncode == 0, "run failed: %r" % (proc.stderr,)
        with open(in_path, "rb") as fh:
            after = fh.read()
        assert after == before, "input file was modified"
        st_after = os.stat(in_path)
        assert st_before.st_mtime == st_after.st_mtime, "input mtime changed"

        # Standard library only: CLI must work with an isolated import path.
        proc = subprocess.run(
            ["python", "-I", "-S", APP, in_path, out_path],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
        )
        assert proc.returncode == 0, (
            "CLI failed under isolated stdlib mode: %r" % (proc.stderr,)
        )
        rows = _read_output(out_path)
        assert rows == [["email", "name"], ["a@b.com", "A2"]], "got %r" % (rows,)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


_CHECKS = {
    "R1": _check_r1,
    "R2": lambda: (_check_r2(), _check_r2_whitespace_and_quotes()),
    "R3": lambda: (_check_r3_header_only(), _check_r3_varied()),
    "R4": _check_r4_input_preserved,
}


def check(requirement_id):
    if requirement_id not in _CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    _CHECKS[requirement_id]()
