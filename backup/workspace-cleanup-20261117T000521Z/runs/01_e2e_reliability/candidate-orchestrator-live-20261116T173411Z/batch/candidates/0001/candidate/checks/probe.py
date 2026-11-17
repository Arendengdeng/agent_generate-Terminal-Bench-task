"""Behavioral probe for the customer-CSV cleaning task.

Each check(requirement_id) runs the CLI at /app/clean.py on fresh fixtures
under /tmp and verifies observable behavior only.
"""

import csv
import hashlib
import os
import re
import subprocess
import sys
import tempfile

APP = "/app"
CLI = os.path.join(APP, "clean.py")
TIMEOUT = 10

STDLIB = {
    "abc", "argparse", "codecs", "collections", "csv", "dataclasses", "enum",
    "functools", "hashlib", "io", "itertools", "json", "operator", "os",
    "pathlib", "re", "shutil", "string", "sys", "textwrap", "typing",
    "warnings", "difflib", "tempfile", "locale", "__future__",
}

REQUIREMENTS = ("R1", "R2", "R3", "R4")


def run_cli(input_path, output_path, args=None):
    cmd = [sys.executable, CLI]
    if args is None:
        cmd += [input_path, output_path]
    else:
        cmd += list(args)
    return subprocess.run(
        cmd, capture_output=True, timeout=TIMEOUT, cwd=APP, text=True
    )


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["email", "name"])
        for row in rows:
            writer.writerow(row)


def write_raw(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def workdir():
    return tempfile.mkdtemp(prefix="probe_", dir="/tmp")


def expect_rows(out_path, expected):
    got = read_rows(out_path)
    assert got, "output file missing or empty: %r" % (out_path,)
    assert got[0] == ["email", "name"], "bad header: %r" % (got[0],)
    body = [r for r in got[1:] if r]
    assert body == expected, "expected rows %r, got %r" % (expected, body)
    assert len(got) == len(expected) + 1, "unexpected extra rows: %r" % (got,)


SAMPLE = [
    ("alice@example.com", "Alice Chen"),
    ("  BOB@Example.com ", "Bob Lee, Jr."),
    ("alice@example.com", "Alice Duplicate"),
    ("carol@example.org", "  Carol  "),
    ("bob@example.com", "Bob Second"),
]
SAMPLE_EXPECTED = [
    ["alice@example.com", "Alice Chen"],
    ["bob@example.com", "Bob Lee, Jr."],
    ["carol@example.org", "Carol"],
]


def check_r1():
    d = workdir()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_csv(inp, SAMPLE)
    proc = run_cli(inp, out)
    assert proc.returncode == 0, "exit code %r stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    assert os.path.isfile(out), "output file not created"
    expect_rows(out, SAMPLE_EXPECTED)


QUOTE_NAME = "quote " + chr(34) + chr(34) + "inside" + chr(34) + chr(34) + " name"
QUOTE_NAME_EXPECTED = "quote " + chr(34) + "inside" + chr(34) + " name"


def check_r2():
    d = workdir()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    # Duplicates with case / whitespace variants, quoted comma fields,
    # quoted email surrounding spaces, doubled quotes, tab whitespace.
    rows = [
        ("  Zed@Example.COM", "  Zed  One, Sr."),
        ("amy@example.com", "Amy"),
        ("zed@example.com", "Zed Duplicate"),
        ("  ZED@example.com  ", "Zed Third"),
        ("amy@example.com", "Amy Again"),
        ("bea@example.net", QUOTE_NAME),
        ("bea@example.net", "Bea Duplicate"),
        (" cid@example.com\t", "Cid\tTabbed "),
        ("dan@Example.com", "Dan, \u4e2d\u6587, x"),
        ("eve@example.com", "  Eve  "),
        ("EVE@EXAMPLE.COM", "Eve Duplicate"),
    ]
    write_csv(inp, rows)
    proc = run_cli(inp, out)
    assert proc.returncode == 0, "exit code %r stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    expect_rows(
        out,
        [
            ["zed@example.com", "Zed  One, Sr."],
            ["amy@example.com", "Amy"],
            ["bea@example.net", QUOTE_NAME_EXPECTED],
            ["cid@example.com", "Cid\tTabbed"],
            ["dan@example.com", "Dan, \u4e2d\u6587, x"],
            ["eve@example.com", "Eve"],
        ],
    )


def check_r3():
    # R3a: header-only input -> header-only output (random file name,
    # so nothing can be keyed off the fixture path).
    d = workdir()
    inp = os.path.join(d, "in_%s.csv" % os.urandom(4).hex())
    out = os.path.join(d, "out.csv")
    write_raw(inp, "email,name\n")
    proc = run_cli(inp, out)
    assert proc.returncode == 0, "exit code %r stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    assert read_rows(out) == [["email", "name"]], "header-only failed: %r" % (
        read_rows(out),
    )

    # R3b: larger, differently shaped input with quoted comma / quote fields.
    d2 = workdir()
    inp2 = os.path.join(d2, "in.csv")
    out2 = os.path.join(d2, "out.csv")
    rows = []
    expected = []
    for i in range(60):
        email = "User%d@Example.com" % i
        name = "User %d" % i
        if i % 7 == 0:
            name = "Doe, Jane %d" % i
        if i % 5 == 0:
            name = "Name " + chr(34) + "Q" + chr(34) + " %d" % i
        rows.append(("  %s " % email, "  %s  " % name))
        if i % 3 == 0:
            rows.append((email.upper(), "DUP %d" % i))
        expected.append([email.lower(), name])
    write_csv(inp2, rows)
    proc = run_cli(inp2, out2)
    assert proc.returncode == 0, "exit code %r stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    expect_rows(out2, expected)

    # R3c: output must be re-parsable as exactly 2 fields per row even when
    # names contain commas / quotes.
    for row in read_rows(out2):
        assert len(row) == 2, "output row not 2 fields: %r" % (row,)


def check_r4():
    # Input bytes preserved.
    d = workdir()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(inp, "wb") as handle:
        handle.write(
            b'email,name\n alice@example.com ,"Alice, Jr."\r\nALICE@example.com,Bob\r\n'
        )
    before = sha(inp)
    proc = run_cli(inp, out)
    assert proc.returncode == 0, "exit code %r stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    assert sha(inp) == before, "input file was modified"
    expect_rows(
        out,
        [["alice@example.com", "Alice, Jr."], ["bob@example.com", "Bob"]],
    )

    # Only stdlib imports in the delivered file.
    with open(CLI, "r", encoding="utf-8") as handle:
        source = handle.read()
    for line in source.splitlines():
        stripped = line.strip()
        if re.match(r"^(import|from)\s+", stripped):
            parts = stripped.replace(",", " ").split()
            mods = []
            if parts[0] == "from":
                mods.append(parts[1])
            else:
                for token in parts[1:]:
                    mods.append(token.split(".")[0])
            for mod in mods:
                assert mod.split(".")[0] in STDLIB, "non-stdlib import: %r" % (stripped,)


def check(requirement_id):
    if requirement_id not in REQUIREMENTS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    globals()["check_" + requirement_id.lower()]()


if __name__ == "__main__":
    for rid in REQUIREMENTS:
        try:
            check(rid)
            print("%s PASS" % rid)
        except AssertionError as exc:
            print("%s FAIL %s" % (rid, exc))
