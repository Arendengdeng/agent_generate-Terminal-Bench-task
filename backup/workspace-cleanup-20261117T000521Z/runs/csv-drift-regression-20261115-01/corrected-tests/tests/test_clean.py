import csv
import io
import os
import subprocess
import sys

import pytest

APP = "/app"
SCRIPT = "/app/clean.py"
TIMEOUT = 10


def run_cli(tmp_path, input_bytes, name="input.csv"):
    inp = tmp_path / name
    inp.write_bytes(input_bytes)
    out = tmp_path / "out.csv"
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(inp), str(out)],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=TIMEOUT,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "CLI exited with %r; stderr=%r" % (proc.returncode, proc.stderr[:2000])
        )
    if not out.exists():
        raise AssertionError("CLI did not create output file")
    return proc, out.read_bytes()


def parse_output(data):
    text = data.decode("utf-8")
    reader = csv.reader(io.StringIO(text, newline=""))
    return [row for row in reader if row != []]


def expected(records):
    seen = set()
    result = []
    for email_raw, name_raw in records:
        email = email_raw.strip().lower()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name_raw.strip()))
    return [("email", "name")] + result


def check(tmp_path, records, csv_text=None):
    if csv_text is None:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["email", "name"])
        for r in records:
            writer.writerow(list(r))
        csv_text = buf.getvalue()
    _, data = run_cli(tmp_path, csv_text.encode("utf-8"))
    rows = parse_output(data)
    exp = expected(records)
    assert rows[0] == ["email", "name"], rows[0]
    assert [tuple(r) for r in rows[1:]] == exp[1:], rows
    return data


def test_basic_dedupe_and_normalization(tmp_path):
    records = [
        ("Alice@Example.com", "Alice"),
        ("  alice@example.com  ", "Alice Dup"),
        ("bob@example.com", "Bob"),
        ("BOB@EXAMPLE.COM", "Bobby"),
        ("carol@example.com", "  Carol  "),
    ]
    data = check(tmp_path, records)
    text = data.decode("utf-8")
    assert parse_output(data)[0] == ["email", "name"]
    assert parse_output(data)[0] == ["email", "name"]


def test_quoted_commas_and_quotes(tmp_path):
    csv_text = (
        'email,name\r\n'
        '"a@x.com","Smith, John"\r\n'
        '"A@X.COM","Other, Name"\r\n'
        'b@x.com,"He said ""hi"""\r\n'
    )
    records = [
        ("a@x.com", 'Smith, John'),
        ("A@X.COM", "Other, Name"),
        ("b@x.com", 'He said "hi"'),
    ]
    _, data = run_cli(tmp_path, csv_text.encode("utf-8"))
    rows = parse_output(data)
    assert rows == [
        ["email", "name"],
        ["a@x.com", "Smith, John"],
        ["b@x.com", 'He said "hi"'],
    ]
    # Round-trip via standard csv reader must preserve the exact name content
    assert rows[1][1] == "Smith, John"
    assert rows[2][1] == 'He said "hi"'


def test_multiline_quoted_field(tmp_path):
    csv_text = (
        "email,name\r\n"
        '"m@x.com","Line1\nLine2"\r\n'
        '"M@X.COM","Other"\r\n'
        'n@x.com,"keep"\r\n'
    )
    _, data = run_cli(tmp_path, csv_text.encode("utf-8"))
    rows = parse_output(data)
    assert rows == [
        ["email", "name"],
        ["m@x.com", "Line1\nLine2"],
        ["n@x.com", "keep"],
    ]


def test_header_only(tmp_path):
    data = check(tmp_path, [], csv_text="email,name\n")
    rows = parse_output(data)
    assert rows == [["email", "name"]]
    text = data.decode("utf-8")
    assert parse_output(data)[0] == ["email", "name"]


def test_header_only_crlf(tmp_path):
    data = check(tmp_path, [], csv_text="email,name\r\n")
    rows = parse_output(data)
    assert rows == [["email", "name"]]


def test_whitespace_padded_emails(tmp_path):
    records = [
        ("  padded@example.com  ", "Nobody"),
        ("other@example.com", "Empty"),
        ("real@example.com", "Real"),
        (" real@example.com", "Real Again"),
        ("\ttab@example.com\t", "Tab"),
        ("second@example.com", "Second"),
    ]
    rows = parse_output(check(tmp_path, records))
    assert rows == [
        ["email", "name"],
        ["padded@example.com", "Nobody"],
        ["other@example.com", "Empty"],
        ["real@example.com", "Real"],
        ["tab@example.com", "Tab"],
        ["second@example.com", "Second"],
    ]


def test_empty_name_preserved_as_empty(tmp_path):
    records = [
        ("a@example.com", ""),
        ("b@example.com", "   "),
        ("A@EXAMPLE.COM", "later"),
    ]
    rows = parse_output(check(tmp_path, records))
    assert rows == [
        ["email", "name"],
        ["a@example.com", ""],
        ["b@example.com", ""],
    ]


def test_first_occurrence_order(tmp_path):
    records = [
        ("z@example.com", "Z"),
        ("a@example.com", "A"),
        ("y@example.com", "Y"),
        ("Z@example.com", "Z2"),
        (" a@Example.com ", "A2"),
    ]
    rows = parse_output(check(tmp_path, records))
    assert [r[0] for r in rows[1:]] == ["z@example.com", "a@example.com", "y@example.com"]
    assert [r[1] for r in rows[1:]] == ["Z", "A", "Y"]


def test_input_not_modified(tmp_path):
    csv_text = (
        "email,name\n"
        "A@X.com,Alpha\n"
        '" a@x.com ","Beta, Gamma"\n'
    )
    inp = tmp_path / "input.csv"
    inp.write_bytes(csv_text.encode("utf-8"))
    before = inp.read_bytes()
    out = tmp_path / "out.csv"
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(inp), str(out)],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr
    assert inp.read_bytes() == before, "input file was modified"


def test_no_stray_files_created_in_cwd(tmp_path):
    csv_text = "email,name\nx@x.com,X\n"
    inp = tmp_path / "input.csv"
    inp.write_bytes(csv_text.encode("utf-8"))
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "out.csv"
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(inp), str(out)],
        cwd=str(work),
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr
    leftovers = os.listdir(str(work))
    assert leftovers == [], "unexpected files created: %r" % leftovers


def test_stdlib_only_imports():
    check_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import ast,sys;"
            "src=open('/app/clean.py',encoding='utf-8').read();"
            "tree=ast.parse(src);"
            "mods=set();"
            "exec('\\n'.join([]))"
            ";"
            "import sys as s;"
            "print([n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)])",
        ],
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert check_proc.returncode == 0, check_proc.stderr
    # Execute the script's module body with stdlib-only sys.path to catch third-party deps
    proc = subprocess.run(
        [sys.executable, "-I", "-S", SCRIPT],
        capture_output=True,
        timeout=TIMEOUT,
    )
    # With no args the script should fail with usage, not ImportError
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "ModuleNotFoundError" not in stderr
    assert "ImportError" not in stderr


@pytest.mark.parametrize("records", [
    [("single@example.com", "Only")],
    [("Mixed@CASE.com", " Mixed Name "), ("mixed@case.com", "Second")],
    [("a+b@x.com", "Plus"), ("A+B@X.com", "Dup")],
])
def test_varied_inputs(tmp_path, records):
    check(tmp_path, records)


def test_large_input_1000_records(tmp_path):
    base = []
    for i in range(600):
        base.append(("user%03d@example.com" % i, "Name %d" % i))
    for i in range(400):
        base.append(("USER%03d@EXAMPLE.COM" % i, "Dup %d" % i))
    rows = parse_output(check(tmp_path, base))
    assert len(rows) == 1 + 600
    assert rows[1][1] == "Name 0"
    assert rows[-1][0] == "user599@example.com"
