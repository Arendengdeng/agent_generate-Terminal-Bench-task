"""Behavioral probe for the CSV cleaning CLI task."""

import csv
import hashlib
import io
import os
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
CLEAN = os.path.join(APP, "clean.py")


def run_clean(input_path, output_path):
    return subprocess.run(
        [sys.executable, CLEAN, input_path, output_path],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def make_case(header, rows):
    base = tempfile.mkdtemp(dir="/tmp", prefix="cleanprobe_")
    inp = os.path.join(base, "input.csv")
    out = os.path.join(base, "output.csv")
    write_csv(inp, header, rows)
    return inp, out


def check_output(inp, out, expected_rows):
    before = hashlib.sha256(open(inp, "rb").read()).hexdigest()
    proc = run_clean(inp, out)
    assert proc.returncode == 0, (
        "nonzero exit %r stderr=%r" % (proc.returncode, proc.stderr)
    )
    assert os.path.isfile(out), "output file not written"
    raw = open(out, "rb").read()
    text = raw.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows, "empty output file"
    assert [c.strip().lower() for c in rows[0]] == ["email", "name"], (
        "bad header %r" % (rows[0],)
    )
    assert rows[1:] == expected_rows, (
        "unexpected rows %r != %r" % (rows[1:], expected_rows)
    )
    after = hashlib.sha256(open(inp, "rb").read()).hexdigest()
    assert before == after, "input file was modified"


def check_r1():
    inp, out = make_case(
        ["email", "name"],
        [["a@x.com", "A"], ["b@x.com", "B"]],
    )
    ok = run_clean(inp, out)
    assert ok.returncode == 0, "nonzero exit %r" % (ok.returncode,)
    check_output(inp, out, [["a@x.com", "A"], ["b@x.com", "B"]])
    # usage error must not be a success exit
    bad = subprocess.run(
        [sys.executable, CLEAN],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )
    assert bad.returncode != 0, "missing args should fail"


def check_r2():
    inp, out = make_case(
        ["email", "name"],
        [
            [" Alice@Example.com ", "Alice Smith"],
            ["bob@example.com", "Bob, Jr."],
            ["alice@example.com", "Alice Jones"],
            ["  carol@example.org  ", 'Carol "C" D'],
            ["BOB@EXAMPLE.COM ", " Bob Brown"],
            ["alice@EXAMPLE.com", "  Alice Final  "],
        ],
    )
    check_output(
        inp,
        out,
        [
            ["alice@example.com", "Alice Final"],
            ["bob@example.com", "Bob Brown"],
            ["carol@example.org", 'Carol "C" D'],
        ],
    )


def check_r3():
    inp, out = make_case(["email", "name"], [])
    check_output(inp, out, [])
    # Varied fixture: last-wins vs first-order mismatch plus quoted commas.
    inp, out = make_case(
        ["email", "name"],
        [
            ["z@example.com", "Zed"],
            ["y@example.com", "Yan"],
            ["M@Example.COM", "First M"],
            ["y@example.com", "Yan, II"],
            ["z@example.com", "Zed Final"],
            ["m@example.com", "M Last"],
            ["w@example.com", "W, \"quoted\""],
        ],
    )
    check_output(
        inp,
        out,
        [
            ["z@example.com", "Zed Final"],
            ["y@example.com", "Yan, II"],
            ["m@example.com", "M Last"],
            ["w@example.com", 'W, "quoted"'],
        ],
    )
    # Empty name after trimming is preserved as empty field.
    inp, out = make_case(["email", "name"], [["p@example.com", "   "]])
    check_output(inp, out, [["p@example.com", ""]])


def check_r4():
    assert sorted(os.listdir(APP)) is not None
    inp, out = make_case(["email", "name"], [["a@x.com", "A"], ["a@x.com", "AA"]])
    before = hashlib.sha256(open(inp, "rb").read()).hexdigest()
    proc = run_clean(inp, out)
    assert proc.returncode == 0, "nonzero exit"
    after = hashlib.sha256(open(inp, "rb").read()).hexdigest()
    assert before == after, "input file was modified"
    env = dict(os.environ)
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        [sys.executable, "-S", "-I", CLEAN, inp, os.path.join(os.path.dirname(out), "o2.csv")],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=env,
    )
    assert proc.returncode == 0, (
        "stdlib-only run failed rc=%r stderr=%r" % (proc.returncode, proc.stderr)
    )


CHECKS = {
    "R1": check_r1,
    "R2": check_r2,
    "R3": check_r3,
    "R4": check_r4,
}


def check(requirement_id):
    if requirement_id not in CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    CHECKS[requirement_id]()
