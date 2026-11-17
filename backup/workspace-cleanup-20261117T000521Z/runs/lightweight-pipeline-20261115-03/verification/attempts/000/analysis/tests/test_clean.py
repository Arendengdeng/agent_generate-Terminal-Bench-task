import csv
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10


def run_clean(input_path, output_path):
    """Run the task CLI; return CompletedProcess, failing on timeout."""
    try:
        return subprocess.run(
            [sys.executable, CLEAN, str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd="/tmp",
        )
    except subprocess.TimeoutExpired:
        pytest.fail("CLI timed out after %s seconds" % TIMEOUT)


def read_output(path):
    """Read the produced output CSV with csv module; fail if missing/malformed."""
    if not os.path.exists(path):
        pytest.fail("output file was not created: %s" % path)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def run_and_check(input_path, tmp_path, name="out.csv"):
    out = os.path.join(str(tmp_path), name)
    proc = run_clean(input_path, out)
    assert proc.returncode == 0, "exit=%r stderr=%r" % (proc.returncode, proc.stderr)
    rows = read_output(out)
    assert rows, "output must contain at least a header row"
    assert rows[0] == ["email", "name"], "unexpected header: %r" % (rows[0],)
    return rows[1:]


def write_input(tmp_path, text, name="in.csv"):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def test_cli_success_exit_code_and_header(tmp_path):
    out = os.path.join(str(tmp_path), "out.csv")
    proc = run_clean(os.path.join(FIXTURES, "order.csv"), out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    rows = read_output(out)
    assert rows[0] == ["email", "name"]
    assert len(rows) == 4


def test_cli_accepts_positional_args_from_any_cwd(tmp_path):
    src = write_input(tmp_path, "email,name\na@example.com,A\n")
    out = os.path.join(str(tmp_path), "sub_out.csv")
    proc = run_clean(src, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    assert read_output(out) == [["email", "name"], ["a@example.com", "A"]]


def test_normalization_dedup_and_quoting(tmp_path):
    rows = run_and_check(os.path.join(FIXTURES, "basic.csv"), tmp_path)
    assert rows == [
        ["alice@example.com", "Alice Chen"],
        ["bob@example.com", "Bob Li"],
        ["carol@example.com", "Carol, Jr."],
        ["dave@example.com", "Dave, Sr."],
    ]


def test_quoted_fields_with_commas_and_escaped_quotes(tmp_path):
    rows = run_and_check(os.path.join(FIXTURES, "quoting.csv"), tmp_path)
    assert rows == [
        ['quo"ted@example.com', 'Ann "Q" Lee'],
        ["comma@example.com", "Doe, John, III"],
        ["leading@example.com", "Spaced Name"],
        ["plain@example.com", "Plain Name"],
        ["quoted@example.com", 'Back"slash \\ name'],
    ]


def test_stable_order_preserved(tmp_path):
    rows = run_and_check(os.path.join(FIXTURES, "order.csv"), tmp_path)
    assert rows == [
        ["zoe@example.com", "Zoe Last"],
        ["amy@example.com", "Amy First"],
        ["bob@example.com", "Bob Middle"],
    ]


def test_output_uses_csv_escaping(tmp_path):
    src = write_input(
        tmp_path,
        'email,name\n"x@example.com","Doe, ""J"" Do"\n',
    )
    out = os.path.join(str(tmp_path), "out.csv")
    proc = run_clean(src, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    with open(out, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    # The name must be CSV-quoted with doubled inner quotes.
    assert '"Doe, ""J"" Do"' in raw
    assert read_output(out) == [["email", "name"], ["x@example.com", 'Doe, "J" Do']]


def test_header_only_input(tmp_path):
    rows = run_and_check(os.path.join(FIXTURES, "header_only.csv"), tmp_path)
    assert rows == []


def test_empty_input_file_produces_only_header(tmp_path):
    src = write_input(tmp_path, "")
    rows = run_and_check(src, tmp_path)
    assert rows == []


def test_duplicate_only_input_yields_single_record(tmp_path):
    src = write_input(
        tmp_path,
        "email,name\n"
        "A@x.com,First\n"
        " a@X.COM ,Second\n"
        "  A@x.com,Third\n",
    )
    rows = run_and_check(src, tmp_path)
    assert rows == [["a@x.com", "First"]]


def test_internal_whitespace_and_case_preserved(tmp_path):
    src = write_input(
        tmp_path,
        'email,name\n"a@example.com","  John   von Neumann  "\n'
        '"A@example.com","john von neumann"\n',
    )
    rows = run_and_check(src, tmp_path)
    assert rows == [["a@example.com", "John   von Neumann"]]


def test_large_input_max_records(tmp_path):
    lines = ["email,name"]
    for i in range(1000):
        lines.append("User%d@Example.com,Name %d" % (i, i))
    src = write_input(tmp_path, "\n".join(lines) + "\n")
    rows = run_and_check(src, tmp_path)
    assert len(rows) == 1000
    assert rows[0] == ["user0@example.com", "Name 0"]
    assert rows[999] == ["user999@example.com", "Name 999"]


def test_large_input_with_many_duplicates(tmp_path):
    lines = ["email,name"]
    for i in range(500):
        lines.append("dup%d@example.com,First %d" % (i, i))
    for i in range(500):
        lines.append(" DUP%d@EXAMPLE.com ,Second %d" % (i, i))
    src = write_input(tmp_path, "\n".join(lines) + "\n")
    rows = run_and_check(src, tmp_path)
    assert len(rows) == 500
    assert rows[0] == ["dup0@example.com", "First 0"]
    assert all(r[1].startswith("First ") for r in rows)


def test_input_file_not_modified(tmp_path):
    src = os.path.join(str(tmp_path), "in.csv")
    orig = os.path.join(FIXTURES, "basic.csv")
    shutil.copyfile(orig, src)
    with open(src, "rb") as fh:
        before = hashlib.sha256(fh.read()).hexdigest()
    out = os.path.join(str(tmp_path), "out.csv")
    proc = run_clean(src, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    with open(src, "rb") as fh:
        after = hashlib.sha256(fh.read()).hexdigest()
    assert before == after


def test_only_stdlib_imports(tmp_path):
    import ast

    with open(CLEAN, "r", encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    allowed = set(sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in allowed, "non-stdlib import: %s" % alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            top = (node.module or "").split(".")[0]
            assert top in allowed, "non-stdlib import: %s" % node.module


def test_no_additional_files_created_in_app(tmp_path):
    before = sorted(os.listdir(APP))
    src = write_input(tmp_path, "email,name\na@example.com,A\n")
    out = os.path.join(str(tmp_path), "out.csv")
    proc = run_clean(src, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    after = sorted(os.listdir(APP))
    assert before == after, "app directory changed: %r -> %r" % (before, after)
