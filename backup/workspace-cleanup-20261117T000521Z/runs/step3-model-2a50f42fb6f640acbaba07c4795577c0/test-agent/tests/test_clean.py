import csv
import os
import subprocess
import sys
import tempfile

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10


def run_clean(input_path, output_path):
    try:
        proc = subprocess.run(
            [sys.executable, CLEAN, input_path, output_path],
            cwd=APP,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError("clean.py did not finish within %s seconds" % TIMEOUT)
    return proc


def read_csv_file(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def run_and_read(tmp_path, input_text=None, fixture=None, name="out.csv"):
    if fixture is not None:
        inp = os.path.join(FIX, fixture)
    else:
        inp = os.path.join(str(tmp_path), "in.csv")
        with open(inp, "w", encoding="utf-8", newline="") as fh:
            fh.write(input_text)
    out = os.path.join(str(tmp_path), name)
    proc = run_clean(inp, out)
    assert proc.returncode == 0, "exit code %r, stderr=%r" % (proc.returncode, proc.stderr)
    assert os.path.isfile(out), "output file was not written"
    return read_csv_file(out)


def test_quoted_commas_and_duplicates(tmp_path):
    rows = run_and_read(tmp_path, fixture="quoted_input.csv")
    assert rows == [
        ["email", "name"],
        ["alice@example.com", "Alice Smith"],
        ["bob@example.com", "Bob, Jr."],
        ["carol@example.com", 'Carol "CJ" Jones'],
        ["dave@example.com", ""],
    ]


def test_order_preserved_first_occurrence(tmp_path):
    rows = run_and_read(tmp_path, fixture="order_input.csv")
    assert rows == [
        ["email", "name"],
        ["z@example.com", "Zed"],
        ["a@example.com", "Ay"],
        ["m@example.com", "M"],
    ]


def test_whitespace_only_trimming(tmp_path):
    rows = run_and_read(tmp_path, fixture="whitespace_input.csv")
    assert rows == [
        ["email", "name"],
        ["u1@example.com", "spaced name"],
        ["u2@example.com", "plain"],
    ]


def test_inline_case_and_comma_fields(tmp_path):
    text = (
        "email,name\n"
        '"  One@Example.com  ","  One, First "\n'
        '"two@example.com","Two"\n'
        'ONE@example.com,One Later\n'
        '"two@EXAMPLE.com","  Two, Second"\n'
        '"three@example.com","Three"\n'
    )
    rows = run_and_read(tmp_path, text)
    assert rows == [
        ["email", "name"],
        ["one@example.com", "One, First"],
        ["two@example.com", "Two"],
        ["three@example.com", "Three"],
    ]


def test_header_only_input(tmp_path):
    rows = run_and_read(tmp_path, "email,name\n")
    assert rows == [["email", "name"]]


def test_header_only_without_trailing_newline(tmp_path):
    rows = run_and_read(tmp_path, "email,name")
    assert rows == [["email", "name"]]


def test_no_duplicates_all_kept_in_order(tmp_path):
    text = "email,name\nb@example.com,B\na@example.com,A\nc@example.com,C\n"
    rows = run_and_read(tmp_path, text)
    assert rows == [
        ["email", "name"],
        ["b@example.com", "B"],
        ["a@example.com", "A"],
        ["c@example.com", "C"],
    ]


def test_duplicate_every_item_collapses_to_one(tmp_path):
    text = "email,name\nx@example.com,First\nX@EXAMPLE.COM,Second\n  x@example.com  ,Third\n"
    rows = run_and_read(tmp_path, text)
    assert rows == [["email", "name"], ["x@example.com", "First"]]


def test_large_input_1000_records(tmp_path):
    lines = ["email,name"]
    expected = [["email", "name"]]
    for i in range(1000):
        email = "user%d@example.com" % (i % 500)
        name = "Name %d" % i
        lines.append("%s,%s" % (email, name))
        if i < 500:
            expected.append([email, name])
    text = "\n".join(lines) + "\n"
    rows = run_and_read(tmp_path, text)
    assert len(rows) == 501
    assert rows == expected


def test_output_is_utf8_csv_and_input_untouched(tmp_path):
    src = os.path.join(str(tmp_path), "input.csv")
    content = "email,name\n  A@B.com ,  Åsa, Name \nA@B.COM,Other\n"
    with open(src, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    with open(src, "rb") as fh:
        before = fh.read()
    out = os.path.join(str(tmp_path), "out.csv")
    proc = run_clean(src, out)
    assert proc.returncode == 0, "exit code %r, stderr=%r" % (proc.returncode, proc.stderr)
    with open(src, "rb") as fh:
        after = fh.read()
    assert before == after, "input file was modified"
    with open(out, "rb") as fh:
        raw = fh.read()
    decoded = raw.decode("utf-8")
    assert decoded
    with open(out, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["email", "name"],
        ["a@b.com", "Åsa, Name"],
    ]


def test_only_stdlib_imports():
    with open(CLEAN, "r", encoding="utf-8") as fh:
        source = fh.read()
    import ast

    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    assert modules, "expected some imports"
    for mod in modules:
        assert mod in sys.stdlib_module_names, "non-stdlib import: %s" % mod
