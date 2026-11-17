import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

APP = "/app"
CLEAN = "/app/clean.py"
TIMEOUT = 10

HEADER = ["email", "name"]


def run_clean(input_text, extra_args=None, encoding="utf-8"):
    """Create a fixture dir, write input, run the CLI. Returns (proc, in_path, out_path, workdir)."""
    workdir = tempfile.mkdtemp(dir="/tmp", prefix="cleantest_")
    in_path = os.path.join(workdir, "input.csv")
    out_path = os.path.join(workdir, "output.csv")
    with open(in_path, "wb") as handle:
        handle.write(input_text.encode(encoding))
    args = [sys.executable, CLEAN]
    if extra_args is None:
        args += [in_path, out_path]
    else:
        args += list(extra_args)
    try:
        proc = subprocess.run(
            args,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, in_path, out_path, workdir
    return proc, in_path, out_path, workdir


def parse_output(out_path):
    if not os.path.exists(out_path):
        raise AssertionError("output file was not created at %s" % out_path)
    data = open(out_path, "rb").read()
    if not data:
        raise AssertionError("output file is empty")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError("output is not valid UTF-8: %r" % (exc,))
    rows = list(csv.reader(io.StringIO(text, newline="")))
    # csv.reader keeps a trailing "" row when the text ends with a newline?
    # It does not: trailing blank line just terminates. Guard anyway.
    return rows, data


def expect_ok(input_text):
    proc, in_path, out_path, workdir = run_clean(input_text)
    if proc is None:
        shutil.rmtree(workdir, ignore_errors=True)
        raise AssertionError("CLI timed out after %ss" % TIMEOUT)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace")
        shutil.rmtree(workdir, ignore_errors=True)
        raise AssertionError(
            "CLI exited with %s; stderr=%r" % (proc.returncode, stderr)
        )
    rows, raw = parse_output(out_path)
    return rows, raw, in_path, out_path, workdir


def assert_rows_equal(actual, expected):
    assert actual[:1] == [HEADER], "first output row must be header email,name, got %r" % (
        actual[:1],
    )
    assert actual[1:] == expected, "rows mismatch: expected %r got %r" % (
        expected,
        actual[1:],
    )


def test_r1_success_exit_code_and_output_file():
    text = "email,name\nalice@example.com,Alice\n"
    proc, in_path, out_path, workdir = run_clean(text)
    try:
        assert proc is not None, "CLI timed out after %ss" % TIMEOUT
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
        rows, raw = parse_output(out_path)
        assert_rows_equal(rows, [["alice@example.com", "Alice"]])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r1_output_path_is_user_supplied_second_arg():
    workdir = tempfile.mkdtemp(dir="/tmp", prefix="cleantest_")
    try:
        in_path = os.path.join(workdir, "in.csv")
        out_path = os.path.join(workdir, "sub", "result.csv")
        os.makedirs(os.path.dirname(out_path))
        with open(in_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("email,name\nx@y.z,X\n")
        try:
            proc = subprocess.run(
                [sys.executable, CLEAN, in_path, out_path],
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("CLI timed out after %ss" % TIMEOUT)
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
        rows, _ = parse_output(out_path)
        assert_rows_equal(rows, [["x@y.z", "X"]])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r1_output_header_and_csv_written_to_spec():
    rows, raw, in_path, out_path, workdir = expect_ok(
        "email,name\nbob@example.com,Bob\n"
    )
    try:
        assert rows[0] == HEADER, "header must be exactly email,name: %r" % (rows[0],)
        assert rows[1:] == [["bob@example.com", "Bob"]]
        raw.decode("utf-8")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r2_normalizes_email_whitespace_and_case():
    text = (
        "email,name\n"
        "  Alice@Example.com ,  Alice Chen\n"
        "\tBOB@Example.COM\t,Bob B\n"
        " alice@example.com ,Alice Again\n"
        "bob@example.com,Bob Doe\n"
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [["alice@example.com", "Alice Chen"], ["bob@example.com", "Bob B"]],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r2_quoted_names_with_commas_and_quotes_preserved():
    text = (
        "email,name\n"
        'bob@example.com,"Doe, Bob"\n'
        'carol@example.org,"Carol ""CC"" Ng"\n'
        ' dan@example.net ,"  Dan  Q.  Public, Jr.  "\n'
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [
                ["bob@example.com", "Doe, Bob"],
                ["carol@example.org", 'Carol "CC" Ng'],
                ["dan@example.net", "Dan  Q.  Public, Jr."],
            ],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r2_output_reparses_to_same_values():
    text = "email,name\nA@B.com,\"Name, With \"\"quotes\"\"\"\n"
    rows, raw, _, _, workdir = expect_ok(text)
    try:
        text_out = raw.decode("utf-8")
        assert "Name, With" in text_out
        # Re-parsing the output must yield exactly the expected cells.
        again = list(csv.reader(io.StringIO(text_out, newline="")))
        assert again == [HEADER, ["a@b.com", 'Name, With "quotes"']], again
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r2_stable_order_first_occurrence_kept():
    text = (
        "email,name\n"
        "c@x.com,First C\n"
        "a@x.com,First A\n"
        "b@x.com,First B\n"
        "B@X.COM,Second B\n"
        "a@x.com,Second A\n"
        "c@x.com,Second C\n"
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [
                ["c@x.com", "First C"],
                ["a@x.com", "First A"],
                ["b@x.com", "First B"],
            ],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r2_first_duplicate_name_with_quotes_kept():
    text = (
        "email,name\n"
        'dup@example.com,"Zed, First"\n'
        "  DUP@Example.com ,Overwritten\n"
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(rows, [["dup@example.com", "Zed, First"]])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r3_header_only_input():
    rows, raw, _, _, workdir = expect_ok("email,name\n")
    try:
        assert rows == [HEADER], "expected only the header row, got %r" % (rows,)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r3_header_only_without_trailing_newline():
    rows, _, _, _, workdir = expect_ok("email,name")
    try:
        assert rows == [HEADER], "expected only the header row, got %r" % (rows,)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r3_other_input_not_hardcoded_sample():
    text = (
        "email,name\n"
        "  Zed@Sample.IO ,Zed\n"
        "amy@other.net,\"Amy, A.\"\n"
        "ZED@sample.io,Zed duplicated\n"
        "amy@OTHER.net,Amy second\n"
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [
                ["zed@sample.io", "Zed"],
                ["amy@other.net", "Amy, A."],
            ],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r3_no_duplicates_all_kept():
    text = (
        "email,name\n"
        "u1@a.com,User One\n"
        "u2@a.com,User Two\n"
        "u3@b.com,\"User, Three\"\n"
        "u4@b.com,User Four\n"
    )
    rows, _, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [
                ["u1@a.com", "User One"],
                ["u2@a.com", "User Two"],
                ["u3@b.com", "User, Three"],
                ["u4@b.com", "User Four"],
            ],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r3_max_size_input_within_time():
    lines = ["email,name"]
    expected = []
    for i in range(1000):
        email = "user%d@ex.com" % i
        lines.append("%s,Name %d" % (email, i))
        expected.append([email, "Name %d" % i])
    # add some duplicates by re-listing half of them (1000 total records)
    lines = ["email,name"]
    expected = []
    for i in range(500):
        lines.append("  User%d@EX.com ,Name %d" % (i, i))
        lines.append("user%d@ex.com,Duplicate %d" % (i, i))
        expected.append(["user%d@ex.com" % i, "Name %d" % i])
    proc, in_path, out_path, workdir = run_clean("\n".join(lines) + "\n")
    try:
        assert proc is not None, "CLI timed out after %ss" % TIMEOUT
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
        rows, _ = parse_output(out_path)
        assert_rows_equal(rows, expected)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r4_input_file_not_modified():
    text = (
        "email,name\r\n"
        "  Alice@Example.com ,  Alice Chen\r\n"
        'bob@example.com,"Doe, Bob"\r\n'
        "ALICE@example.com,Alice Chen (dup)\r\n"
    )
    workdir = tempfile.mkdtemp(dir="/tmp", prefix="cleantest_")
    try:
        in_path = os.path.join(workdir, "input.csv")
        out_path = os.path.join(workdir, "output.csv")
        with open(in_path, "wb") as handle:
            handle.write(text.encode("utf-8"))
        before = open(in_path, "rb").read()
        try:
            proc = subprocess.run(
                [sys.executable, CLEAN, in_path, out_path],
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("CLI timed out after %ss" % TIMEOUT)
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
        after = open(in_path, "rb").read()
        assert after == before, "input file was modified by the tool"
        rows, _ = parse_output(out_path)
        assert_rows_equal(
            rows,
            [["alice@example.com", "Alice Chen"], ["bob@example.com", "Doe, Bob"]],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_r4_stdlib_only_imports():
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy, sys, importlib.abc\n"
                "import importlib.util\n"
                "class Blocker(importlib.abc.MetaPathFinder):\n"
                "    def find_spec(self, name, path, target=None):\n"
                "        top = name.split('.')[0]\n"
                "        if top in ('pip','setuptools','numpy','pandas','requests'):\n"
                "            raise ImportError('third-party module blocked: ' + name)\n"
                "        return None\n"
                "sys.meta_path.insert(0, Blocker())\n"
                "sys.argv = ['clean.py']\n"
                "runpy.run_path('/app/clean.py', run_name='__main__')\n"
            ),
        ],
        cwd="/tmp",
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
    )
    assert proc.returncode != 0 or b"Traceback" not in proc.stderr
    # With no arguments, the program must not import third-party modules.
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "third-party module blocked" not in stderr, stderr


def test_r4_output_uses_csv_quoting_not_naive_concat():
    text = (
        "email,name\n"
        'x@y.com,"A, B"\n'
        'q@y.com,"Has ""inner"" quotes"\n'
    )
    rows, raw, _, _, workdir = expect_ok(text)
    try:
        assert_rows_equal(
            rows,
            [["x@y.com", "A, B"], ["q@y.com", 'Has "inner" quotes']],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
