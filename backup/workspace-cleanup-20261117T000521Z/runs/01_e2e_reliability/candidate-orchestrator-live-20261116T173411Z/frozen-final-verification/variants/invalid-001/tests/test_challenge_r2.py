"""Additional public-CLI tests for Contract requirement R2.

These tests are additive: they only exercise the documented command
``python /app/clean.py <input.csv> <output.csv>`` with valid inputs and check
the observable CSV output (header, normalized e-mails, trimmed names, stable
first-occurrence dedup, CSV escaping) plus exit code and input preservation.
"""

import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

CLEAN = "/app/clean.py"
TIMEOUT = 10
HEADER = ["email", "name"]


def _run(input_text, output_name="people.csv", input_name="in.csv"):
    workdir = tempfile.mkdtemp(dir="/tmp", prefix="challenge_")
    in_path = os.path.join(workdir, input_name)
    out_path = os.path.join(workdir, output_name)
    with open(in_path, "wb") as handle:
        handle.write(input_text.encode("utf-8"))
    proc = subprocess.run(
        [sys.executable, CLEAN, in_path, out_path],
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
    )
    return proc, in_path, out_path, workdir


def _parse_csv_file(path):
    assert os.path.exists(path), "output file %s was not created" % path
    data = open(path, "rb").read()
    assert data, "output file %s is empty" % path
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError("output is not valid UTF-8: %r" % (exc,))
    return [row for row in csv.reader(io.StringIO(text, newline="")) if row != []]


def _check(input_text, expected_rows, output_name="people.csv"):
    try:
        proc, in_path, out_path, workdir = _run(input_text, output_name=output_name)
    except subprocess.TimeoutExpired:
        raise AssertionError("CLI timed out after %ss" % TIMEOUT)
    try:
        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r" % (proc.returncode, stderr)
        )
        rows = _parse_csv_file(out_path)
        assert rows[:1] == [HEADER], "expected header email,name, got %r" % (rows[:1],)
        assert rows[1:] == expected_rows, (
            "expected rows %r, got %r" % (expected_rows, rows[1:])
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_challenge_first_quoted_duplicate_wins_over_later_plain():
    # First occurrence of bob@example.com carries the quoted comma name.
    text = (
        "email,name\n"
        '  Bob@Example.COM  ,"Doe, Bob"\n'
        " bob@example.com ,Bob Doe\n"
        "  Alice@Example.com ,  Alice Chen\n"
        "ALICE@example.com,Alice Chen (dup)\n"
    )
    _check(
        text,
        [["bob@example.com", "Doe, Bob"], ["alice@example.com", "Alice Chen"]],
    )


def test_challenge_later_duplicates_are_discarded_not_merged():
    # Later duplicates must be dropped entirely; the name must not be merged.
    text = (
        "email,name\n"
        "carol@example.org,Carol First\n"
        "  CAROL@Example.org ,Carol Second\n"
        "carol@example.org,Carol Third\n"
        "dave@example.net,Dave\n"
    )
    _check(
        text,
        [["carol@example.org", "Carol First"], ["dave@example.net", "Dave"]],
    )


def test_challenge_first_seen_order_preserved_with_mixed_quoting():
    text = (
        "email,name\n"
        'zed@example.com,"Zed, Z."\n'
        "  AMY@Example.COM ,  Amy A.\n"
        'Zed@EXAMPLE.com,"Later, Zed"\n'
        "amy@example.com,Amy Again\n"
        '  quinn@example.com ,"Quinn ""Q"" Q"\n'
    )
    _check(
        text,
        [
            ["zed@example.com", "Zed, Z."],
            ["amy@example.com", "Amy A."],
            ["quinn@example.com", 'Quinn "Q" Q'],
        ],
    )


def test_challenge_multiline_quoted_name_preserved():
    text = (
        "email,name\n"
        'lee@example.com,"Lee\nSecond Line"\n'
        "LEE@example.com,Dropped\n"
    )
    _check(text, [["lee@example.com", "Lee\nSecond Line"]])


def test_challenge_output_written_to_second_positional_argument():
    text = (
        "email,name\n"
        'zed@sample.io,"Zed, Z"\n'
        " zed@SAMPLE.io ,Zed Later\n"
    )
    _check(
        text,
        [["zed@sample.io", "Zed, Z"]],
        output_name="sub_people.csv",
    )


def test_challenge_input_file_unchanged_by_challenge_fixture():
    text = (
        "email,name\n"
        '  Bob@Example.COM  ,"Doe, Bob"\n'
        " bob@example.com ,Bob Doe\n"
    )
    try:
        proc, in_path, out_path, workdir = _run(text)
    except subprocess.TimeoutExpired:
        raise AssertionError("CLI timed out after %ss" % TIMEOUT)
    try:
        assert proc.returncode == 0, (
            "expected exit code 0, got %s; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
        with open(in_path, "rb") as handle:
            assert handle.read() == text.encode("utf-8"), "input file was modified"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
