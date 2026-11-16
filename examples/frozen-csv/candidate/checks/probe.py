#!/usr/bin/env python3
"""Behavioral self-check for the customer CSV cleaning task."""

import csv
import hashlib
import io
import os
import subprocess
import sys
import tempfile

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
COMMAND_TIMEOUT_SEC = 10

REQUIREMENTS = ("R1", "R2", "R3", "R4")


def _run(in_path, out_path):
    return subprocess.run(
        [sys.executable, CLEAN, in_path, out_path],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _write_input(tmpdir, text):
    path = os.path.join(tmpdir, "input.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def _expected(text):
    """Reference model: csv parsing, strip/lower email, strip name, first wins."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    out = ["email,name"]
    seen = set()
    for row in rows[1:]:
        if not row:
            continue
        email = row[0].strip().lower()
        name = row[1].strip() if len(row) > 1 else ""
        if email in seen:
            continue
        seen.add(email)
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerow([email, name])
        out.append(buf.getvalue().rstrip("\n"))
    return "\n".join(out) + "\n"


def _read_output(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _clean_run(tmpdir, text):
    """Run the tool on ``text``; return (result, output_text)."""
    in_path = _write_input(tmpdir, text)
    out_path = os.path.join(tmpdir, "output.csv")
    if os.path.exists(out_path):
        os.remove(out_path)
    before = hashlib.sha256(open(in_path, "rb").read()).hexdigest()
    result = _run(in_path, out_path)
    after = hashlib.sha256(open(in_path, "rb").read()).hexdigest()
    assert before == after, "input file was modified by the tool"
    out_text = _read_output(out_path) if os.path.exists(out_path) else None
    return result, out_text


FIXTURES = {
    "quoted_comma": (
        "email,name\n"
        ' alice@example.com ,"Doe, Jane"\n'
        'ALICE@example.com ,"Doe, Jane (dup)"\n'
        'bob@example.com ,"  Smith, Bob "\n'
        'Bob@Example.COM,"Smith, Bob again"\n'
        'carol@example.com,"O\'Neil, ""CJ"""\n'
    ),
    "whitespace_upper": (
        "email,name\n"
        'x@y.io ,  Zeta  \n'
        '  X@Y.IO,Other\n'
        'm@n.org,Mid\n'
    ),
    "header_only": "email,name\n",
    "no_trailing_newline": 'email,name\nq@w.r,Last No Newline',
    "single": 'email,name\nsolo@example.com,Solo\n',
    "many_dups": (
        "email,name\n"
        + "".join("u%d@example.com,Name %d\n" % (i % 7, i) for i in range(30))
    ),
    "no_dups_spaces": (
        "email,name\n"
        " a@example.com , A Name \n"
        "b@example.com,\"B, Name\"\n"
        "c@example.com,C\n"
    ),
}


def _check_r1(tmpdir):
    text = FIXTURES["quoted_comma"]
    result, out_text = _clean_run(tmpdir, text)
    assert result.returncode == 0, (
        "expected exit code 0, got %r (stderr=%r)" % (result.returncode, result.stderr)
    )
    assert out_text is not None, "output file was not written"
    rows = list(csv.reader(io.StringIO(out_text, newline="")))
    assert rows and rows[0] == ["email", "name"], "bad header: %r" % (rows[:1],)
    assert out_text == _expected(text), (
        "output mismatch.\nexpected=%r\nactual=%r" % (_expected(text), out_text)
    )


def _check_r2(tmpdir):
    for key in ("quoted_comma", "whitespace_upper", "many_dups", "no_dups_spaces"):
        text = FIXTURES[key]
        result, out_text = _clean_run(tmpdir, text)
        assert result.returncode == 0, "fixture %s: exit %r stderr=%r" % (
            key,
            result.returncode,
            result.stderr,
        )
        assert out_text == _expected(text), (
            "fixture %s: output mismatch.\nexpected=%r\nactual=%r"
            % (key, _expected(text), out_text)
        )
    result, out_text = _clean_run(tmpdir, FIXTURES["quoted_comma"])
    assert result.returncode == 0, "dedup fixture exit %r" % (result.returncode,)
    rows = list(csv.reader(io.StringIO(out_text, newline="")))[1:]
    assert rows == [
        ["alice@example.com", "Doe, Jane"],
        ["bob@example.com", "Smith, Bob"],
        ["carol@example.com", 'O\'Neil, "CJ"'],
    ], "unexpected dedup result: %r" % (rows,)


def _check_r3(tmpdir):
    result, out_text = _clean_run(tmpdir, FIXTURES["header_only"])
    assert result.returncode == 0, "header-only: exit %r" % (result.returncode,)
    assert out_text == "email,name\n", "header-only output: %r" % (out_text,)
    result, out_text = _clean_run(tmpdir, FIXTURES["single"])
    assert result.returncode == 0, "single: exit %r" % (result.returncode,)
    assert out_text == "email,name\nsolo@example.com,Solo\n", "single: %r" % (out_text,)
    result, out_text = _clean_run(tmpdir, FIXTURES["no_trailing_newline"])
    assert result.returncode == 0, "no-newline: exit %r" % (result.returncode,)
    assert out_text == "email,name\nq@w.r,Last No Newline\n", (
        "no trailing newline fixture: %r" % (out_text,)
    )
    text = (
        "email,name\n"
        ' zz@example.org ,"  Quoted, Person  "\n'
        "ZZ@EXAMPLE.ORG,dupe\n"
        "aa@example.net ,Plain\n"
    )
    result, out_text = _clean_run(tmpdir, text)
    assert result.returncode == 0, "second set: exit %r" % (result.returncode,)
    assert out_text == (
        "email,name\n"
        "zz@example.org,\"Quoted, Person\"\n"
        "aa@example.net,Plain\n"
    ), "second set content: %r" % (out_text,)


def _check_r4(tmpdir):
    in_path = _write_input(tmpdir, FIXTURES["quoted_comma"])
    before = open(in_path, "rb").read()
    out_path = os.path.join(tmpdir, "output.csv")
    result = _run(in_path, out_path)
    assert result.returncode == 0, "R4 run failed: %r" % (result.returncode,)
    assert open(in_path, "rb").read() == before, "input file content changed"
    env = dict(os.environ)
    env["PYTHONPATH"] = APP
    importing = subprocess.run(
        [sys.executable, "-c", "import clean"],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=env,
    )
    assert importing.returncode == 0, "clean.py import failed: %r" % (
        importing.stderr,
    )
    stdlib_only = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, clean;"
            "bad=[m for m in sys.modules if m.split('.')[0] in "
            "('numpy','pandas','requests')];"
            "print(bad)",
        ],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=env,
    )
    assert stdlib_only.returncode == 0, "stdlib import check failed: %r" % (
        stdlib_only.stderr,
    )
    assert stdlib_only.stdout.strip() == "[]", "non-stdlib modules loaded: %r" % (
        stdlib_only.stdout,
    )


def check(requirement_id):
    if requirement_id not in REQUIREMENTS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="probe-") as tmpdir:
        if requirement_id == "R1":
            _check_r1(tmpdir)
        elif requirement_id == "R2":
            _check_r2(tmpdir)
        elif requirement_id == "R3":
            _check_r3(tmpdir)
        elif requirement_id == "R4":
            _check_r4(tmpdir)
