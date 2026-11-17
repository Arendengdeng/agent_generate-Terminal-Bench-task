"""R4: the tool must not modify the input file (byte-for-byte preservation).

These checks use inputs whose trailing shape (blank line, CRLF, BOM) would be
"normalized" by any implementation that rewrites or cleans up the input file.
"""

import csv
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

APP = "/app"
CLEAN = os.path.join(APP, "clean.py")
TIMEOUT = 10


def run_clean(input_path, output_path):
    return subprocess.run(
        [sys.executable, CLEAN, input_path, output_path],
        cwd=tempfile.gettempdir(),
        capture_output=True,
        timeout=TIMEOUT,
    )


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_output(path):
    assert os.path.isfile(path), "expected output CSV was not written"
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


@pytest.fixture
def workdir():
    d = tempfile.mkdtemp(prefix="clean-immutable-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write_input(workdir, text):
    path = os.path.join(workdir, "in.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def check_result(proc, output_path):
    assert proc.returncode == 0, (
        "clean.py exited with %r; stderr=%r" % (proc.returncode, proc.stderr)
    )
    data = read_output(output_path)
    assert data, "output CSV is empty"
    assert data[0] == ["email", "name"], "unexpected header: %r" % (data[0],)
    return data


def test_trailing_blank_line_input_preserved(workdir):
    src = write_input(
        workdir, "email,name\nAlice@Example.com,  Alice  \n\n"
    )
    with open(src, "rb") as fh:
        before_bytes = fh.read()
    before = hashlib.sha256(before_bytes).hexdigest()
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == [["alice@example.com", "Alice"]]
    with open(src, "rb") as fh:
        after_bytes = fh.read()
    assert after_bytes == before_bytes, "input file was modified"
    assert sha(src) == before


def test_multiple_trailing_blank_lines_and_crlf_preserved(workdir):
    text = (
        "email,name\r\n"
        "Bob@X.org,Bob\r\n"
        "\"C@X.org\",\"Cee, Jr\"\r\n"
        "\r\n"
        "\r\n"
    )
    src = write_input(workdir, text)
    with open(src, "rb") as fh:
        before_bytes = fh.read()
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == [["bob@x.org", "Bob"], ["c@x.org", "Cee, Jr"]]
    with open(src, "rb") as fh:
        assert fh.read() == before_bytes, "input file was modified"


def test_missing_final_newline_input_preserved(workdir):
    text = "email,name\nDup@X.org,First\ndup@x.org,Second"
    src = write_input(workdir, text)
    with open(src, "rb") as fh:
        before_bytes = fh.read()
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == [["dup@x.org", "First"]]
    with open(src, "rb") as fh:
        assert fh.read() == before_bytes, "input file was modified"


def test_input_unchanged_on_repeated_runs_and_output_elsewhere(workdir):
    src = write_input(
        workdir,
        "email,name\n"
        "  Dup@X.org  ,  First  \n"
        "dup@x.org,Second\n"
        "other@x.org,\"  quoted, name  \"\n"
        "\n",
    )
    with open(src, "rb") as fh:
        before_bytes = fh.read()
    for i in range(2):
        out = os.path.join(workdir, "out%d.csv" % i)
        proc = run_clean(src, out)
        data = check_result(proc, out)
        assert data[1:] == [
            ["dup@x.org", "First"],
            ["other@x.org", "quoted, name"],
        ]
        with open(src, "rb") as fh:
            assert fh.read() == before_bytes, "input file was modified"
        assert os.listdir(workdir).count("in.csv") == 1
