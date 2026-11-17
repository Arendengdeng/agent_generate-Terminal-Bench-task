import csv
import hashlib
import io
import os
import subprocess
import sys

import pytest

SCRIPT = "/app/clean.py"
TIMEOUT = 10
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def run_clean(args):
    return subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        cwd="/tmp",
    )


def read_rows(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        pytest.fail("file is not valid UTF-8: %s" % path)
    return list(csv.reader(io.StringIO(text, newline="")))


def read_fixture(name):
    return read_rows(os.path.join(FIXTURES, name))


def write_input(tmp_path, text, name="input.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def run_ok(src, out):
    result = run_clean([src, out])
    assert result.returncode == 0, "stderr: %r" % result.stderr
    assert os.path.exists(out), "output file was not written"
    return read_rows(out)


# ---------------------------------------------------------------- R1
def test_r1_success_exit_code_and_output_contract(tmp_path):
    src = write_input(tmp_path, "email,name\na@example.com,Ann\n")
    out = str(tmp_path / "out.csv")
    rows = run_ok(src, out)
    assert rows[0] == ["email", "name"]
    assert rows == [["email", "name"], ["a@example.com", "Ann"]]
    # Default output location is the path given by the second argument.
    assert os.path.isfile(out)


def test_r1_wrong_arity_does_not_succeed(tmp_path):
    src = write_input(tmp_path, "email,name\na@example.com,Ann\n")
    out = str(tmp_path / "out.csv")
    result = run_clean([src])
    assert result.returncode != 0
    result = run_clean([src, out, "extra.csv"])
    assert result.returncode != 0
    assert not os.path.exists(out)


def test_r1_existing_output_overwritten(tmp_path):
    src = write_input(tmp_path, "email,name\nx@example.com,X\n")
    out = tmp_path / "out.csv"
    out.write_text("stale,header\n1,2\n3,4\n", encoding="utf-8")
    rows = run_ok(src, str(out))
    assert rows == [["email", "name"], ["x@example.com", "X"]]


# ---------------------------------------------------------------- R2
def test_r2_last_name_wins_first_order(tmp_path):
    src = os.path.join(FIXTURES, "last_wins.csv")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [
        ["email", "name"],
        ["p@example.com", "P Three"],
        ["q@example.com", "Q Two"],
        ["r@example.com", "R One"],
    ]


def test_r2_whitespace_and_case_normalization(tmp_path):
    content = (
        "email,name\n"
        "  Alice@Example.COM ,  Alice One  \n"
        "alice@example.com,Alice Two\n"
        "\tbob@example.com\t,\tBob  \n"
        " BOB@EXAMPLE.COM , Bob Last \n"
    )
    src = write_input(tmp_path, content)
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [
        ["email", "name"],
        ["alice@example.com", "Alice Two"],
        ["bob@example.com", "Bob Last"],
    ]


def test_r2_quoted_fields_with_commas_and_quotes(tmp_path):
    src = os.path.join(FIXTURES, "mixed.csv")
    out = str(tmp_path / "out.csv")
    rows = run_ok(src, out)
    assert rows == read_fixture("mixed_expected.csv")
    assert rows == [
        ["email", "name"],
        ["zoe@example.com", 'Zoe "M" Final'],
        ["mike@example.com", "Zoe Three"],
    ]
    # Output bytes must themselves obey standard CSV quoting rules.
    with open(out, "rb") as handle:
        raw_text = handle.read().decode("utf-8")
    assert list(csv.reader(io.StringIO(raw_text, newline=""))) == rows


def test_r2_empty_name_trimmed_and_last_wins(tmp_path):
    src = os.path.join(FIXTURES, "empty_name.csv")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [["email", "name"], ["q@example.com", ""]]


def test_r2_empty_name_replaced_by_later_name(tmp_path):
    content = "email,name\n  Quux@Example.COM  ,   \nQuux@example.com,Final\n"
    src = write_input(tmp_path, content)
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [["email", "name"], ["quux@example.com", "Final"]]


def test_r2_crlf_input(tmp_path):
    content = "email,name\r\nM@Example.com,M One\r\nm@example.com,M Two\r\n"
    src = write_input(tmp_path, content)
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [["email", "name"], ["m@example.com", "M Two"]]


# ---------------------------------------------------------------- R3
def test_r3_header_only_input(tmp_path):
    src = write_input(tmp_path, "email,name\n")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [["email", "name"]]


def test_r3_header_only_fixture(tmp_path):
    src = os.path.join(FIXTURES, "header_only.csv")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [["email", "name"]]


def test_r3_order_not_derived_from_sample(tmp_path):
    content = (
        "email,name\n"
        "zzz@example.com,Zed\n"
        "aaa@example.com,Ay\n"
        "zzz@example.com,Zed2\n"
    )
    src = write_input(tmp_path, content)
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [
        ["email", "name"],
        ["zzz@example.com", "Zed2"],
        ["aaa@example.com", "Ay"],
    ]


def test_r3_many_records(tmp_path):
    lines = ["email,name"]
    expected = [["email", "name"]]
    for i in range(300):
        email = "user%03d@example.com" % (299 - i)
        lines.append("%s,Name %d" % (email, i))
        expected.append([email, "Name %d" % i])
    lines.append("user150@example.com,Updated 150")
    lines.append(" user000@EXAMPLE.com ,Updated 0")
    expected[151][1] = "Updated 150"
    expected[300][1] = "Updated 0"
    src = write_input(tmp_path, "\n".join(lines) + "\n")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == expected


def test_r3_single_record(tmp_path):
    src = write_input(tmp_path, "email,name\nsolo@example.com,  Solo Person  \n")
    out = str(tmp_path / "out.csv")
    assert run_ok(src, out) == [
        ["email", "name"],
        ["solo@example.com", "Solo Person"],
    ]


# ---------------------------------------------------------------- R4
def test_r4_input_file_unmodified(tmp_path):
    original = (
        "email,name\n"
        "  Alice@Example.com ,Alice\n"
        'bob@example.com,"Bob, Jr."\n'
        "Alice@example.com,Alice L\n"
    )
    src = write_input(tmp_path, original)
    before_hash = hashlib.sha256(open(src, "rb").read()).hexdigest()
    out = str(tmp_path / "out.csv")
    run_ok(src, out)
    after_bytes = open(src, "rb").read()
    assert hashlib.sha256(after_bytes).hexdigest() == before_hash
    assert after_bytes.decode("utf-8") == original


def test_r4_runs_without_preexisting_bytecode_or_extra_modules(tmp_path):
    # In a stripped directory (no /app imports, no site packages beyond stdlib
    # of the interpreter running the test) the CLI must still work.
    src = write_input(tmp_path, "email,name\nu@example.com,U\n")
    out = str(tmp_path / "out.csv")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-S", "-E", SCRIPT, src, out],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        cwd=str(tmp_path),
        env=env,
    )
    assert result.returncode == 0, "stderr: %r" % result.stderr
    assert read_rows(out) == [["email", "name"], ["u@example.com", "U"]]
