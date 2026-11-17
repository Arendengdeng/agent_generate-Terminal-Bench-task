import csv
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


def make_temp():
    return tempfile.mkdtemp(prefix="clean_cli_", dir="/tmp")


def test_cli_accepts_positional_arguments():
    d = make_temp()
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(inp, "w", encoding="utf-8", newline="") as fh:
        fh.write("email,name\n  Mixed@Case.COM ,  Mixed  \n")
    proc = run_clean(inp, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(out), "output file not written"
    with open(out, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["email", "name"]
    assert rows[1:] == [["mixed@case.com", "Mixed"]]
