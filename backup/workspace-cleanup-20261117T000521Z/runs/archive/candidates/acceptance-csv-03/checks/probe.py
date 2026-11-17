"""Behavioral probe for the CSV cleaning repair task."""

import csv
import io
import os
import subprocess
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
CLEAN = "/app/clean.py"


def _run(inp_path, out_path):
    return subprocess.run(
        ["python", CLEAN, inp_path, out_path],
        cwd=APP,
        timeout=COMMAND_TIMEOUT_SEC,
        capture_output=True,
        text=True,
    )


def _case(rows_text, name="case"):
    """Write input fixture to a tmp dir, run CLI, return (proc, out_text, input_bytes)."""
    d = tempfile.mkdtemp(prefix="csvprobe_", dir="/tmp")
    inp = os.path.join(d, name + "_in.csv")
    out = os.path.join(d, name + "_out.csv")
    data = rows_text.encode("utf-8")
    with open(inp, "wb") as f:
        f.write(data)
    proc = _run(inp, out)
    with open(inp, "rb") as f:
        after = f.read()
    text = None
    if os.path.exists(out):
        with open(out, "r", encoding="utf-8", newline="") as f:
            text = f.read()
    return proc, text, data, after


def _parse(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def _assert_ok(proc, text):
    assert proc.returncode == 0, (
        "expected exit 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
    )
    assert text is not None, "output file was not written"


SAMPLE = (
    "email,name\n"
    "Alice@Example.com ,Alice Chen\n"
    'bob@example.com,"Bob, Jr."\n'
    "alice@example.com,Alice Chen\n"
    "  carol@example.com ,\"  Carol  \"\n"
    "bob@example.com,Robert\n"
)

SAMPLE_EXPECTED = [
    ["email", "name"],
    ["alice@example.com", "Alice Chen"],
    ["bob@example.com", "Bob, Jr."],
    ["carol@example.com", "Carol"],
]


def _check_r1():
    proc, text, _, _ = _case(SAMPLE, "r1")
    _assert_ok(proc, text)
    rows = _parse(text)
    assert rows, "output is empty"
    assert rows[0] == ["email", "name"], "bad header: %r" % (rows[0],)
    # positional args honored: second path receives the output
    d = tempfile.mkdtemp(prefix="csvprobe_r1b_", dir="/tmp")
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(inp, "w", encoding="utf-8") as f:
        f.write("email,name\nx@y.com,X\n")
    proc = _run(inp, out)
    assert proc.returncode == 0, "exit %r stderr=%r" % (proc.returncode, proc.stderr)
    assert os.path.exists(out), "output file not created at given path"


def _check_r2():
    proc, text, _, _ = _case(SAMPLE, "r2")
    _assert_ok(proc, text)
    rows = _parse(text)
    assert rows == SAMPLE_EXPECTED, "got %r" % (rows,)

    tricky = (
        "email,name\n"
        '  A@B.COM  ,"Doe, ""John"""\n'
        "a@b.com,Other\n"
        "c@d.org,\"  spaced, name  \"\n"
        "E@F.net,First\n"
        "e@f.net ,Second\n"
    )
    proc, text, _, _ = _case(tricky, "r2b")
    _assert_ok(proc, text)
    rows = _parse(text)
    expected = [
        ["email", "name"],
        ["a@b.com", 'Doe, "John"'],
        ["c@d.org", "spaced, name"],
        ["e@f.net", "First"],
    ]
    assert rows == expected, "tricky case got %r" % (rows,)


def _check_r3():
    proc, text, _, _ = _case("email,name\n", "r3h")
    _assert_ok(proc, text)
    rows = _parse(text)
    assert rows == [["email", "name"]], "header-only got %r" % (rows,)

    proc, text, _, _ = _case("email,name\n", "r3h2")
    _assert_ok(proc, text)
    assert _parse(text) == [["email", "name"]]

    # not hardcoded to the sample: different data
    other = (
        "email,name\n"
        ' z@z.io ,"  Zed  "\n'
        "y@y.io,Why\n"
        "Z@Z.IO,Again\n"
    )
    proc, text, _, _ = _case(other, "r3b")
    _assert_ok(proc, text)
    rows = _parse(text)
    expected = [
        ["email", "name"],
        ["z@z.io", "Zed"],
        ["y@y.io", "Why"],
    ]
    assert rows == expected, "other case got %r" % (rows,)

    # single record, no trailing newline
    proc, text, _, _ = _case('email,name\nonly@one.com,"A, B"', "r3c")
    _assert_ok(proc, text)
    assert _parse(text) == [["email", "name"], ["only@one.com", "A, B"]], (
        "single record got %r" % (_parse(text),)
    )


def _check_r4():
    proc, text, original, after = _case(SAMPLE, "r4")
    _assert_ok(proc, text)
    assert after == original, "input file was modified"

    # no third-party imports: run with site-packages disabled
    d = tempfile.mkdtemp(prefix="csvprobe_r4b_", dir="/tmp")
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(inp, "w", encoding="utf-8") as f:
        f.write(SAMPLE)
    proc = subprocess.run(
        ["python", "-S", CLEAN, inp, out],
        cwd=APP,
        timeout=COMMAND_TIMEOUT_SEC,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, "run with -S failed: %r" % (proc.stderr,)
    assert os.path.exists(out), "-S run produced no output"
    with open(inp, "rb") as f:
        assert f.read() == SAMPLE.encode("utf-8"), "input modified by -S run"


_REQUIREMENTS = {
    "R1": _check_r1,
    "R2": _check_r2,
    "R3": _check_r3,
    "R4": _check_r4,
}


def check(requirement_id):
    fn = _REQUIREMENTS.get(requirement_id)
    if fn is None:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    fn()
