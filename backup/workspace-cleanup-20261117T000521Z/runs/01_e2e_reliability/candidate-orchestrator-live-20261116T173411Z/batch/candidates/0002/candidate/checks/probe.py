"""Behavioral probe for the customer-list cleaning CLI task.

Each requirement is checked by running `python /app/clean.py` on fixtures
created under /tmp and inspecting the produced CSV files.
"""

import ast
import csv
import hashlib
import io
import os
import subprocess
import sys
import tempfile

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
TIMEOUT = 10


def _run(args, cwd=APP):
    return subprocess.run(
        ["python", CLEAN] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def _write(tmpdir, name, content):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return path


def _parse(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def _run_case(tmpdir, raw_input, tag):
    src = _write(tmpdir, "in_%s.csv" % tag, raw_input)
    dst = os.path.join(tmpdir, "out_%s.csv" % tag)
    if os.path.exists(dst):
        os.unlink(dst)
    proc = _run([src, dst])
    assert proc.returncode == 0, (
        "expected exit code 0 for %s, got %r (stderr=%r)"
        % (tag, proc.returncode, proc.stderr))
    assert os.path.exists(dst), "no output file written for %s" % tag
    with open(dst, "rb") as handle:
        raw_out = handle.read()
    text = raw_out.decode("utf-8")
    return text, _parse(text)


def _expect_rows(text, rows, label):
    parsed = _parse(text)
    assert parsed == rows, "%s: expected rows %r, got %r (raw=%r)" % (
        label, rows, parsed, text)


SIMPLE_IN = (
    "email,name\n"
    "  Alice@Example.com ,  Alice Chen\n"
    'bob@example.com,"Doe, Bob"\n'
    "ALICE@example.com,Alice Chen (dup)\n"
    'carol@example.org,"Carol ""CC"" Ng"\n'
    " bob@EXAMPLE.com , Bob Doe\n"
    "dave@example.com,  Dave Park\n"
)

SIMPLE_OUT = [
    ["email", "name"],
    ["alice@example.com", "Alice Chen"],
    ["bob@example.com", "Doe, Bob"],
    ["carol@example.org", 'Carol "CC" Ng'],
    ["dave@example.com", "Dave Park"],
]


def _check_r1(tmpdir):
    text, _ = _run_case(tmpdir, SIMPLE_IN, "r1")
    _expect_rows(text, SIMPLE_OUT, "R1 simple case")


def _check_r2(tmpdir):
    text, _ = _run_case(tmpdir, SIMPLE_IN, "r2")
    _expect_rows(text, SIMPLE_OUT, "R2 normalise/dedupe")

    # Later duplicates must not override the first name; names keep their
    # case and inner spacing.
    case_in = (
        "email,name\n"
        "x@a.io,First\n"
        "y@a.io,Mixed Case Name\n"
        " X@A.IO ,Second\n"
        "Y@A.IO,other\n"
        "z@a.io,  spaced   inside name  \n"
        "q@a.io,\"Smith,  Jane\"\n"
    )
    text2, _ = _run_case(tmpdir, case_in, "r2b")
    expected2 = [
        ["email", "name"],
        ["x@a.io", "First"],
        ["y@a.io", "Mixed Case Name"],
        ["z@a.io", "spaced   inside name"],
        ["q@a.io", "Smith,  Jane"],
    ]
    _expect_rows(text2, expected2, "R2 complex normalisation")

    # Tabs around fields and CRLF line endings.
    crlf_in = (
        "email,name\r\n"
        "\tTab@Ex.com\t,\tTab Person\t\r\n"
        "tab@ex.com,Tab Person\r\n"
    )
    text3, _ = _run_case(tmpdir, crlf_in, "r2c")
    _expect_rows(text3, [
        ["email", "name"],
        ["tab@ex.com", "Tab Person"],
    ], "R2 CRLF/tab whitespace")


def _check_r3(tmpdir):
    header_in = "email,name\n"
    text, _ = _run_case(tmpdir, header_in, "r3_header")
    _expect_rows(text, [["email", "name"]], "R3 header only")
    assert text.strip() == "email,name", (
        "R3: header-only output should contain only the header, got %r" % text)

    # Different legal input that does not resemble the sample.
    other_in = (
        "email,name\n"
        'zz@example.net,"Zed, ""Z"" Zulu"\n'
        "aa@example.net,Ay\n"
        "ZZ@EXAMPLE.NET,ZZ duplicate\n"
        "mm@example.net,   \n"
        "bb@example.net,Bee\n"
    )
    text2, _ = _run_case(tmpdir, other_in, "r3_other")
    _expect_rows(text2, [
        ["email", "name"],
        ["zz@example.net", 'Zed, "Z" Zulu'],
        ["aa@example.net", "Ay"],
        ["mm@example.net", ""],
        ["bb@example.net", "Bee"],
    ], "R3 alternate input")

    # Larger generated input: all duplicates after the first are dropped,
    # first-appearance order preserved.
    lines = ["email,name"]
    expected = [["email", "name"]]
    for i in range(100):
        lines.append("  P%d@Example.COM  ,Person %d" % (i, i))
        expected.append(["p%d@example.com" % i, "Person %d" % i])
    for i in range(99, -1, -1):
        lines.append("P%d@example.com,Again %d" % (i, i))
    big = "\n".join(lines) + "\n"
    text3, _ = _run_case(tmpdir, big, "r3_big")
    _expect_rows(text3, expected, "R3 large generated input")


def _stdlib_only(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    allowed = set(sys.stdlib_module_names)
    return sorted(m for m in modules if m not in allowed)


def _check_r4(tmpdir):
    src = _write(tmpdir, "in_r4.csv", SIMPLE_IN)
    with open(src, "rb") as handle:
        before = hashlib.sha256(handle.read()).hexdigest()
    dst = os.path.join(tmpdir, "out_r4.csv")
    proc = _run([src, dst])
    assert proc.returncode == 0, "R4: run failed: %r" % (proc.stderr,)
    with open(src, "rb") as handle:
        after = hashlib.sha256(handle.read()).hexdigest()
    assert before == after, "R4: input file was modified"

    bad = _stdlib_only(CLEAN)
    assert not bad, "R4: clean.py imports non-stdlib modules: %r" % (bad,)

    # Must work from another cwd without relying on extra files in /app.
    src2 = _write(tmpdir, "in_r4b.csv", "email,name\nA@b.io, Ann\n")
    dst2 = os.path.join(tmpdir, "out_r4b.csv")
    proc2 = _run([src2, dst2], cwd=tmpdir)
    assert proc2.returncode == 0, (
        "R4: run from another cwd failed: %r" % (proc2.stderr,))
    with open(dst2, encoding="utf-8") as handle:
        assert _parse(handle.read()) == [
            ["email", "name"], ["a@b.io", "Ann"]], "R4: wrong output from other cwd"


CHECKS = {
    "R1": _check_r1,
    "R2": _check_r2,
    "R3": _check_r3,
    "R4": _check_r4,
}


def check(requirement_id):
    if requirement_id not in CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="probe_") as tmpdir:
        CHECKS[requirement_id](tmpdir)


if __name__ == "__main__":
    for rid in sorted(CHECKS):
        check(rid)
        print("ok", rid)
