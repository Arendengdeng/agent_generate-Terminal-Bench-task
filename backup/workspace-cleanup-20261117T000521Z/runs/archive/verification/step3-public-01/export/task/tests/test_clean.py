import csv
import hashlib
import os
import subprocess
import sys
import tempfile

APP = "/app/clean.py"
TIMEOUT = 10


def run_clean(input_path, output_path):
    return subprocess.run(
        [sys.executable, APP, input_path, output_path],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def read_output_rows(output_path):
    assert os.path.exists(output_path), "output file was not created"
    with open(output_path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows, "output CSV is empty (missing header)"
    return rows


def assert_output(output_path, expected_pairs):
    rows = read_output_rows(output_path)
    assert rows[0] == ["email", "name"], "header must be exactly email,name: %r" % (rows[0],)
    body = [r for r in rows[1:] if r != []]
    for r in body:
        assert len(r) == 2, "each output row must have exactly 2 fields: %r" % (r,)
    assert body == [list(p) for p in expected_pairs], "unexpected body: %r" % (body,)


def make_temp():
    return tempfile.mkdtemp(prefix="clean_test_", dir="/tmp")


# ---------------------------------------------------------------- R1

def test_cli_success_exit_zero_and_writes_output():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(inp, "email,name\na@example.com,Alice\nb@example.com,Bob\n")
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(out, [("a@example.com", "Alice"), ("b@example.com", "Bob")])


def test_output_is_utf8_and_header_first():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(inp, "email,name\nx@example.com,Normal\n")
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    data = read_bytes(out)
    text = data.decode("utf-8")
    assert text.splitlines()[0].replace("\ufeff", "") == "email,name"


# ---------------------------------------------------------------- R2

def test_dedupe_case_and_whitespace_normalization():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(
        inp,
        "email,name\n"
        "  Alice@Example.COM  ,  Alice Smith  \n"
        "bob@example.com,Bob\n"
        "alice@example.com,Alice Duplicate\n"
        "BOB@EXAMPLE.COM ,Bob Dup\n"
        "carol@example.com,  Carol  \n",
    )
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(
        out,
        [
            ("alice@example.com", "Alice Smith"),
            ("bob@example.com", "Bob"),
            ("carol@example.com", "Carol"),
        ],
    )


def test_quoted_fields_with_commas_quotes_newlines():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(
        inp,
        'email,name\n'
        '"a@example.com","Smith, John"\n'
        '"b@example.com","He said ""hi"" to me"\n'
        '"c@example.com","Line1\nLine2"\n'
        '" a@example.com ","Another, Name"\n',
    )
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(
        out,
        [
            ("a@example.com", "Smith, John"),
            ("b@example.com", 'He said "hi" to me'),
            ("c@example.com", "Line1\nLine2"),
        ],
    )


def test_duplicate_keeps_first_name_and_order():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(
        inp,
        "email,name\n"
        "z@example.com,First-Z\n"
        "a@example.com,First-A\n"
        "z@example.com,Second-Z\n"
        "m@example.com,Only-M\n"
        "a@example.com,Second-A\n",
    )
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(
        out,
        [
            ("z@example.com", "First-Z"),
            ("a@example.com", "First-A"),
            ("m@example.com", "Only-M"),
        ],
    )


def test_output_value_requiring_escaping_roundtrips():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(
        inp,
        "email,name\n"
        '"u@example.com","  Tab, and ""quote"" here  "\n',
    )
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(out, [("u@example.com", 'Tab, and "quote" here')])


# ---------------------------------------------------------------- R3

def test_header_only_input_gives_header_only_output():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(inp, "email,name\n")
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(out, [])


def test_all_duplicates_of_single_email():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(
        inp,
        "email,name\n"
        "Same@Example.com,One\n"
        " same@example.COM ,Two\n"
        "SAME@EXAMPLE.COM,Three\n",
    )
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(out, [("same@example.com", "One")])


def test_varied_inputs_no_hardcoding():
    d = make_temp()
    out = os.path.join(d, "out.csv")
    cases = [
        ("email,name\nq@q.org,X\n", [("q@q.org", "X")]),
        (
            "email,name\np@a.io,P\nr@a.io,Q\nQ@p.io,R\n",
            [("p@a.io", "P"), ("r@a.io", "Q"), ("q@p.io", "R")],
        ),
        (
            'email,name\n"e@e.e","Doe, Jane"\nf@f.f,"O""Neil"\n',
            [("e@e.e", "Doe, Jane"), ("f@f.f", 'O"Neil')],
        ),
    ]
    for idx, (content, expected) in enumerate(cases):
        inp = os.path.join(d, "in%d.csv" % idx)
        write_text(inp, content)
        proc = run_clean(inp, out)
        assert proc.returncode == 0, proc.stderr
        assert_output(out, expected)


def test_large_input_up_to_limit():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    lines = ["email,name"]
    expected = []
    # 1000 data records, duplicated pairs: 500 unique emails repeated twice.
    for i in range(500):
        lines.append("U%d@Ex.com,Name%d" % (i, i))
        lines.append(" u%d@ex.COM ,Dup%d" % (i, i))
        expected.append(("u%d@ex.com" % i, "Name%d" % i))
    write_text(inp, "\n".join(lines) + "\n")
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert_output(out, expected)


# ---------------------------------------------------------------- R4

def test_input_file_not_modified():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    content = (
        "email,name\n"
        "  A@B.com ,,x,\n".replace(",,x,", '"  A  "')  # keep valid structure
    )
    content = "email,name\n  A@B.com ,  A  \n  a@b.com ,B\n"
    write_text(inp, content)
    before = hashlib.sha256(read_bytes(inp)).hexdigest()
    before_mtime = os.stat(inp).st_mtime_ns
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    after = hashlib.sha256(read_bytes(inp)).hexdigest()
    assert after == before, "input file content changed"
    assert os.stat(inp).st_mtime_ns == before_mtime, "input file mtime changed"
    assert read_bytes(inp).decode("utf-8") == content


def test_stdlib_only_no_third_party_imports():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    write_text(inp, "email,name\na@b.c,N\n")
    # Isolated mode: ignores user site-packages, fails on non-stdlib imports
    # that are not installed; stdlib-only script must still run.
    proc = subprocess.run(
        [sys.executable, "-I", APP, inp, out],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr
    assert_output(out, [("a@b.c", "N")])
