"""Behavioral tests for /app/clean.py (customer list cleaner CLI)."""

import csv
import os
import subprocess
import sys

import pytest

APP = "/app/clean.py"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10


def run_cli(in_path, out_path):
    return subprocess.run(
        [sys.executable, APP, in_path, out_path],
        capture_output=True,
        timeout=TIMEOUT,
        cwd="/tmp",
    )


def write_csv(path, header, rows, quoting=csv.QUOTE_MINIMAL):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=quoting)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def read_output(out_path):
    assert os.path.exists(out_path), "output file was not created"
    with open(out_path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def run_and_check(in_path, out_path):
    proc = run_cli(in_path, out_path)
    assert proc.returncode == 0, (
        "expected exit code 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
    )
    return read_output(out_path)


def assert_header(rows):
    assert rows, "output is empty; expected header row"
    assert rows[0] == ["email", "name"], "unexpected header: %r" % (rows[0],)


def test_mixed_fixture_normalization_and_dedup(tmp_path):
    out = str(tmp_path / "out.csv")
    rows = run_and_check(os.path.join(FIXTURES, "mixed.csv"), out)
    assert_header(rows)
    assert rows[1:] == [
        ["alice@example.com", "Alice Smith"],
        ["bob@example.com", "Bob, Jr."],
        ["carol@example.org", 'Carol "C" Jones'],
        ["dave@example.net", ""],
    ]


def test_header_only_input_produces_header_only_output(tmp_path):
    out = str(tmp_path / "out.csv")
    rows = run_and_check(os.path.join(FIXTURES, "header_only.csv"), out)
    assert rows == [["email", "name"]]


def test_header_only_without_trailing_newline(tmp_path):
    in_path = str(tmp_path / "in.csv")
    with open(in_path, "w", encoding="utf-8", newline="") as fh:
        fh.write("email,name")
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [["email", "name"]]


def test_quoted_fields_with_commas_quotes_and_blank_names(tmp_path):
    in_path = str(tmp_path / "in.csv")
    write_csv(
        in_path,
        ["email", "name"],
        [
            ["a@x.com", 'Doe, "John"'],
            ["b@x.com", "Plain"],
            ["c@x.com", ""],
        ],
    )
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [
        ["email", "name"],
        ["a@x.com", 'Doe, "John"'],
        ["b@x.com", "Plain"],
        ["c@x.com", ""],
    ]


def test_whitespace_and_case_dedup_keeps_first_name_and_order(tmp_path):
    in_path = str(tmp_path / "in.csv")
    write_csv(
        in_path,
        ["email", "name"],
        [
            ["  First@Mail.COM ", "  First Name  "],
            ["second@mail.com", "Second"],
            ["FIRST@MAIL.COM", "Other Name"],
            ["first@mail.com", "Third"],
            ["\tsecond@MAIL.com", "Second Again"],
        ],
    )
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [
        ["email", "name"],
        ["first@mail.com", "First Name"],
        ["second@mail.com", "Second"],
    ]


def test_all_fields_quoted_input(tmp_path):
    in_path = str(tmp_path / "in.csv")
    write_csv(
        in_path,
        ["email", "name"],
        [
            ["X@Y.COM", "One, Two"],
            ["x@y.com", "Duplicate"],
            ["z@y.com", "Three"],
        ],
        quoting=csv.QUOTE_ALL,
    )
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [
        ["email", "name"],
        ["x@y.com", "One, Two"],
        ["z@y.com", "Three"],
    ]


def test_output_uses_csv_escaping(tmp_path):
    in_path = str(tmp_path / "in.csv")
    write_csv(in_path, ["email", "name"], [["q@x.com", 'Smith, J "Q"']])
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [["email", "name"], ["q@x.com", 'Smith, J "Q"']]
    with open(out, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # The comma and quotes in the name must be escaped so the row stays on one line.
    assert len(lines) == 2, "output rows are not properly escaped: %r" % (text,)


def test_crlf_input_with_quoted_commas(tmp_path):
    in_path = str(tmp_path / "in.csv")
    data = 'email,name\r\nA@B.C,"Last, First"\r\na@b.c,"Other, Name"\r\n'
    with open(in_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(data)
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert rows == [["email", "name"], ["a@b.c", "Last, First"]]


def test_generated_large_distinct_input_preserves_order(tmp_path):
    in_path = str(tmp_path / "in.csv")
    expected = []
    records = []
    for i in range(1000):
        email = "user%04d@example.com" % i
        name = "User %d, Esq." % i if i % 3 == 0 else "User %d" % i
        records.append([email, name])
        expected.append([email, name])
    write_csv(in_path, ["email", "name"], records)
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert_header(rows)
    assert rows[1:] == expected


def test_generated_large_duplicates(tmp_path):
    in_path = str(tmp_path / "in.csv")
    records = []
    expected = []
    for i in range(1000):
        idx = i % 500
        email = "user%03d@example.com" % idx
        case_email = email.upper() if i % 2 else "  " + email + "  "
        name = "Name %d" % i
        records.append([case_email, name])
        if i < 500:
            expected.append([email, name])
    write_csv(in_path, ["email", "name"], records)
    out = str(tmp_path / "out.csv")
    rows = run_and_check(in_path, out)
    assert_header(rows)
    assert rows[1:] == expected


def test_input_file_is_not_modified(tmp_path):
    in_path = str(tmp_path / "in.csv")
    content = 'email,name\nA@B.C,"Last, First"\na@b.c,Other\n'
    with open(in_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    before = open(in_path, "rb").read()
    out = str(tmp_path / "out.csv")
    run_and_check(in_path, out)
    after = open(in_path, "rb").read()
    assert after == before, "input file was modified"


def test_success_with_input_in_readonly_like_paths(tmp_path):
    # Ensures run only needs the two positional params and stdlib.
    in_path = str(tmp_path / "input.csv")
    write_csv(in_path, ["email", "name"], [["Solo@Ex.com", " Solo "]])
    out = str(tmp_path / "nested_out.csv")
    proc = run_cli(in_path, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    rows = read_output(out)
    assert rows == [["email", "name"], ["solo@ex.com", "Solo"]]


def test_no_third_party_imports(tmp_path):
    # Running the CLI in a subprocess with only stdlib on the path is implicit;
    # explicitly verify clean.py imports resolve to stdlib/builtin modules.
    code = (
        "import ast,sys\n"
        "src=open('/app/clean.py',encoding='utf-8').read()\n"
        "tree=ast.parse(src)\n"
        "mods=set()\n"
        "for n in ast.walk(tree):\n"
        "    if isinstance(n,ast.Import):\n"
        "        for a in n.names: mods.add(a.name.split('.')[0])\n"
        "    elif isinstance(n,ast.ImportFrom) and n.level==0 and n.module:\n"
        "        mods.add(n.module.split('.')[0])\n"
        "import importlib.util\n"
        "bad=[]\n"
        "for m in sorted(mods):\n"
        "    if m in sys.builtin_module_names: continue\n"
        "    spec=importlib.util.find_spec(m)\n"
        "    origin=(spec.origin or '') if spec else ''\n"
        "    if 'site-packages' in origin or 'dist-packages' in origin:\n"
        "        bad.append(m)\n"
        "print('BAD:'+','.join(bad))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=TIMEOUT, cwd="/tmp"
    )
    assert proc.returncode == 0, "inspection failed: %r" % (proc.stderr,)
    text = proc.stdout.decode()
    assert "BAD:" in text
    assert text.strip().endswith("BAD:"), "third-party imports found: %r" % (text,)


def test_wrong_argument_count_is_not_success(tmp_path):
    # Two positional params are required; calling without output must not silently succeed.
    proc = subprocess.run(
        [sys.executable, APP, str(tmp_path / "missing.csv")],
        capture_output=True,
        timeout=TIMEOUT,
        cwd="/tmp",
    )
    assert proc.returncode != 0
