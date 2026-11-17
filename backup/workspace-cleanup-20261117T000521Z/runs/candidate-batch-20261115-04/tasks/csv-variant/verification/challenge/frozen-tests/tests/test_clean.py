import csv
import hashlib
import os
import shutil
import subprocess
import sys
import time

import pytest

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10


def run_clean(in_path, out_path, cwd="/app"):
    """Run the task CLI, assert exit code 0 and that the output exists."""
    proc = subprocess.run(
        [sys.executable, CLEAN, in_path, out_path],
        cwd=cwd,
        capture_output=True,
        timeout=TIMEOUT,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "clean.py exited with %r; stderr=%r"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
    if not os.path.exists(out_path):
        raise AssertionError("clean.py did not create output file %r" % out_path)
    return proc


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)


def expected_rows(rows):
    """Reference semantics computed independently with csv module."""
    order = []
    last_name = {}
    for row in rows:
        email = row[0].strip().lower()
        name = row[1].strip()
        if email not in last_name:
            order.append(email)
        last_name[email] = name
    return [["email", "name"]] + [[e, last_name[e]] for e in order]


def assert_canonical(out_rows, expected):
    if not out_rows:
        raise AssertionError("output CSV is empty; expected header row")
    assert out_rows[0] == ["email", "name"]
    assert out_rows[1:] == expected[1:]


def hash_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def test_success_exit_zero_and_header(tmp_path):
    inp = os.path.join(FIXTURES, "whitespace_case.csv")
    shutil.copy(inp, tmp_path / "in.csv")
    out = tmp_path / "out.csv"
    proc = run_clean(str(tmp_path / "in.csv"), str(out))
    assert proc.returncode == 0
    rows = read_csv(str(out))
    assert rows[0] == ["email", "name"]


def test_sample_like_contract_input(tmp_path):
    inp = os.path.join(FIXTURES, "sample_like.csv")
    out = tmp_path / "out.csv"
    run_clean(inp, str(out))
    rows = read_csv(str(out))
    assert rows[0] == ["email", "name"]
    assert rows[1:] == [
        ["alice@example.com", "Alice S. (updated)"],
        ["bob@example.com", "Bob Jones"],
        ["carol@example.com", "Carol"],
        ["dave@example.com", 'Dave "The D" Davis'],
    ]


def test_whitespace_case_and_last_name(tmp_path):
    inp = os.path.join(FIXTURES, "whitespace_case.csv")
    out = tmp_path / "out.csv"
    run_clean(inp, str(out))
    rows = read_csv(str(out))
    assert rows == [
        ["email", "name"],
        ["a@x.com", "Third A"],
        ["b@x.com", "Padded B2"],
        ["c@x.com", "C, with comma"],
    ]


def test_quotes_commas_newlines_roundtrip(tmp_path):
    inp = os.path.join(FIXTURES, "quotes.csv")
    out = tmp_path / "out.csv"
    run_clean(inp, str(out))
    rows = read_csv(str(out))
    assert rows == [
        ["email", "name"],
        ["q@example.com", 'Quote " and , comma'],
        ["r@example.com", "Plain"],
    ]


def test_header_only_input(tmp_path):
    inp = os.path.join(FIXTURES, "header_only.csv")
    out = tmp_path / "out.csv"
    run_clean(inp, str(out))
    rows = read_csv(str(out))
    assert rows == [["email", "name"]]


def test_first_appearance_order_with_dupes(tmp_path):
    rows_in = [
        ["email", "name"],
        ["m@e.com", "M1"],
        ["z@e.com", "Z1"],
        ["M@E.COM", "M2"],
        ["  a@e.com ", "A1"],
        ["m@e.com", "  M3  "],
        ["b@e.com", "B1"],
        ["a@e.com", "A2"],
        ["z@e.com", "Z2"],
    ]
    in_path = str(tmp_path / "in.csv")
    out_path = str(tmp_path / "out.csv")
    write_csv(in_path, rows_in)
    run_clean(in_path, out_path)
    out_rows = read_csv(out_path)
    assert_canonical(out_rows, [
        ["email", "name"],
        ["m@e.com", "M3"],
        ["z@e.com", "Z2"],
        ["a@e.com", "A2"],
        ["b@e.com", "B1"],
    ])


def test_single_row_and_unique_rows(tmp_path):
    rows_in = [
        ["email", "name"],
        ["solo@e.com", "Only"],
    ]
    in_path = str(tmp_path / "in.csv")
    out_path = str(tmp_path / "out.csv")
    write_csv(in_path, rows_in)
    run_clean(in_path, out_path)
    assert read_csv(out_path) == [["email", "name"], ["solo@e.com", "Only"]]

    rows_in2 = [
        ["email", "name"],
        ["e1@e.com", "N1"],
        ["e2@e.com", "N2"],
        ["e3@e.com", "N3"],
    ]
    in_path2 = str(tmp_path / "in2.csv")
    out_path2 = str(tmp_path / "out2.csv")
    write_csv(in_path2, rows_in2)
    run_clean(in_path2, out_path2)
    assert read_csv(out_path2) == rows_in2


def test_name_only_whitespace_stripped_inner_preserved(tmp_path):
    rows_in = [
        ["email", "name"],
        ["u@e.com", "  spaced  , kept  "],
        ["v@e.com", "\ttabbed\t"],
    ]
    in_path = str(tmp_path / "in.csv")
    out_path = str(tmp_path / "out.csv")
    write_csv(in_path, rows_in)
    run_clean(in_path, out_path)
    rows = read_csv(out_path)
    assert rows == [
        ["email", "name"],
        ["u@e.com", "spaced  , kept"],
        ["v@e.com", "tabbed"],
    ]


def test_input_not_modified(tmp_path):
    orig = os.path.join(FIXTURES, "sample_like.csv")
    inp = tmp_path / "in.csv"
    shutil.copy(orig, inp)
    before = hash_file(str(inp))
    out = tmp_path / "out.csv"
    run_clean(str(inp), str(out))
    assert hash_file(str(inp)) == before
    with open(str(inp), "r", encoding="utf-8", newline="") as fh:
        assert fh.read() == open(orig, "r", encoding="utf-8", newline="").read()


def test_output_uses_csv_escaping(tmp_path):
    rows_in = [
        ["email", "name"],
        ["x@e.com", "Doe, Jane"],
        ["y@e.com", 'He said "hi"'],
        ["z@e.com", "plain no comma"],
    ]
    in_path = str(tmp_path / "in.csv")
    out_path = str(tmp_path / "out.csv")
    write_csv(in_path, rows_in)
    run_clean(in_path, out_path)
    with open(out_path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert read_csv(out_path) == rows_in
    # fields containing comma or quote must be escaped in the raw text
    assert '"Doe, Jane"' in text
    assert '"He said ""hi"""' in text


def test_located_outside_app_cwd(tmp_path):
    inp = os.path.join(FIXTURES, "whitespace_case.csv")
    out = tmp_path / "out.csv"
    run_clean(inp, str(out), cwd="/tmp")
    assert read_csv(str(out))[1:] == [
        ["a@x.com", "Third A"],
        ["b@x.com", "Padded B2"],
        ["c@x.com", "C, with comma"],
    ]


def test_large_input_1000_records(tmp_path):
    rows_in = [["email", "name"]]
    for i in range(1000):
        email = "User%d@Example.COM" % (i % 250)
        pad = " " * (i % 3)
        rows_in.append([pad + email + pad, "Name %d" % i])
    in_path = str(tmp_path / "in.csv")
    out_path = str(tmp_path / "out.csv")
    write_csv(in_path, rows_in)
    start = time.time()
    run_clean(in_path, out_path)
    elapsed = time.time() - start
    assert elapsed < TIMEOUT
    expected = expected_rows(rows_in[1:])
    assert read_csv(out_path) == expected
    assert len(expected) - 1 == 250


def test_randomized_vs_reference(tmp_path):
    import random
    rng = random.Random(1234)
    names = ["Ann", " A, B ", 'Q "x"', "  T\t", "Zed"]
    emails = ["a@e.com", " A@E.com ", "b@e.com", "B@e.COM", "c@e.com"]
    for trial in range(5):
        rows_in = [["email", "name"]]
        for _ in range(rng.randint(1, 30)):
            rows_in.append([rng.choice(emails), rng.choice(names)])
        in_path = str(tmp_path / ("in%d.csv" % trial))
        out_path = str(tmp_path / ("out%d.csv" % trial))
        write_csv(in_path, rows_in)
        run_clean(in_path, out_path)
        assert read_csv(out_path) == expected_rows(rows_in[1:])
