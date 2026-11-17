"""Behavioral probe for the customer-list cleaning CLI task."""

import csv
import io
import os
import subprocess
import tempfile

APP_DIR = "/app"
APP_SCRIPT = "/app/clean.py"
COMMAND_TIMEOUT_SEC = 10

REQUIREMENT_IDS = ["R1", "R2", "R3", "R4"]


def _run(args):
    return subprocess.run(
        ["python3", APP_SCRIPT] + list(args),
        cwd=APP_DIR,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _write_tmp(directory, name, text, newline=None):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline=newline or "") as f:
        f.write(text)
    return path


def _parse_csv_bytes(raw, label):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError("%s: output is not valid UTF-8 (%s)" % (label, exc))
    return list(csv.reader(io.StringIO(text, newline="")))


def _clean_to_rows(directory, name, content, label, newline=None):
    in_path = _write_tmp(directory, name + ".in.csv", content, newline)
    out_path = os.path.join(directory, name + ".out.csv")
    proc = _run([in_path, out_path])
    assert proc.returncode == 0, "%s: expected exit code 0, got %d (stderr=%r)" % (
        label,
        proc.returncode,
        proc.stderr[-800:],
    )
    assert os.path.isfile(out_path), "%s: output file was not written" % label
    with open(out_path, "rb") as f:
        raw = f.read()
    return in_path, out_path, _parse_csv_bytes(raw, label)


def _check_rows(rows, expected, label):
    assert rows, "%s: output is empty" % label
    assert rows[0] == ["email", "name"], "%s: expected header ['email','name'], got %r" % (
        label,
        rows[0],
    )
    data = rows[1:]
    assert data == expected, "%s: expected rows %r, got %r" % (label, expected, data)


def _case_basic(directory):
    content = (
        "email,name\n"
        "  Alice@Example.COM ,  Alice Smith  \n"
        "bob@example.com,Bob\n"
        "ALICE@example.com,Alice Duplicate\n"
    )
    _, _, rows = _clean_to_rows(directory, "basic", content, "basic")
    _check_rows(
        rows,
        [
            ["alice@example.com", "Alice Smith"],
            ["bob@example.com", "Bob"],
        ],
        "basic",
    )


def _case_quoted(directory):
    content = (
        "email,name\r\n"
        '"smith@example.com","Smith, Anna"\r\n'
        '"  SMITH@example.com  ","Smith, Anna (dup)"\r\n'
        '"lee@example.com","Lee, ""Junior"""\r\n'
        '"JOY@example.com","Joy"\r\n'
        '"joy@example.com ","Joy Again"\r\n'
    )
    _, _, rows = _clean_to_rows(directory, "quoted", content, "quoted")
    _check_rows(
        rows,
        [
            ["smith@example.com", "Smith, Anna"],
            ["lee@example.com", 'Lee, "Junior"'],
            ["joy@example.com", "Joy"],
        ],
        "quoted",
    )


def _case_unicode_name(directory):
    content = 'email,name\nZed@Example.com ,"张 ,  三"\nzed@example.com,other\n'
    _, _, rows = _clean_to_rows(directory, "unicode_name", content, "unicode_name")
    _check_rows(rows, [["zed@example.com", "张 ,  三"]], "unicode_name")


def _case_header_only(directory):
    _, _, rows = _clean_to_rows(directory, "header_only", "email,name\n", "header_only")
    assert rows == [["email", "name"]], "header_only: expected only header, got %r" % (rows,)


def _case_header_only_crlf(directory):
    _, _, rows = _clean_to_rows(directory, "header_only_crlf", "email,name\r\n", "header_only_crlf")
    assert rows == [["email", "name"]], "header_only_crlf: expected only header, got %r" % (rows,)


def _case_other_data(directory):
    content = (
        "email,name\n"
        "carol@x.org ,Carol\n"
        "  dave@y.net,Dave  \n"
        "carol@x.org,Carol Second\n"
        'eve@z.io,"Eve, E."\n'
    )
    _, _, rows = _clean_to_rows(directory, "other", content, "other")
    _check_rows(
        rows,
        [
            ["carol@x.org", "Carol"],
            ["dave@y.net", "Dave"],
            ["eve@z.io", "Eve, E."],
        ],
        "other",
    )


def _case_roundtrip_output(directory):
    content = 'email,name\n"q@example.com","Doe, John ""JD"""\n'
    _, out_path, rows = _clean_to_rows(directory, "roundtrip", content, "roundtrip")
    _check_rows(rows, [["q@example.com", 'Doe, John "JD"']], "roundtrip")
    with open(out_path, "rb") as f:
        raw = f.read()
    assert raw.count(b'"') >= 4, "roundtrip: output does not appear CSV-escaped: %r" % raw


def _require_all(cases):
    failures = []
    for case in cases:
        try:
            case()
        except AssertionError as exc:
            failures.append(str(exc))
    assert not failures, "; ".join(failures)


def _check_r1():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        _case_basic(d)
        _case_quoted(d)

        proc = _run([])
        assert proc.returncode != 0, "R1: expected non-zero exit code with no args"
        proc = _run(["only_one.csv"])
        assert proc.returncode != 0, "R1: expected non-zero exit code with one arg"

        missing = os.path.join(d, "missing.csv")
        out = os.path.join(d, "missing.out.csv")
        proc = _run([missing, out])
        assert proc.returncode != 0, "R1: expected non-zero exit code for missing input"
        assert not os.path.exists(out), "R1: output written despite failed input read"


def _check_r2():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        _require_all(
            [
                lambda: _case_basic(d),
                lambda: _case_quoted(d),
                lambda: _case_unicode_name(d),
                lambda: _case_roundtrip_output(d),
            ]
        )


def _check_r3():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        _case_header_only(d)
        _case_header_only_crlf(d)
        _case_other_data(d)


def _check_r4():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        content = "email,name\n ann@example.com , Ann \nbob@example.com,Bob\nANN@example.com,Ann2\n"
        in_path = _write_tmp(d, "preserve.in.csv", content)
        with open(in_path, "rb") as f:
            before = f.read()
        before_stat = os.stat(in_path)
        out_path = os.path.join(d, "preserve.out.csv")
        proc = _run([in_path, out_path])
        assert proc.returncode == 0, "R4: expected exit code 0, got %d" % proc.returncode
        with open(in_path, "rb") as f:
            after = f.read()
        after_stat = os.stat(in_path)
        assert before == after, "R4: input file contents were modified"
        assert before_stat.st_size == after_stat.st_size, "R4: input file size changed"
        assert before_stat.st_mtime_ns == after_stat.st_mtime_ns, "R4: input file mtime changed"


def check(requirement_id):
    if requirement_id not in REQUIREMENT_IDS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    globals()["_check_" + requirement_id.lower()]()
