import csv
import io
import ast
import os
import subprocess
import sys

APP = "/app"
SCRIPT = "/app/clean.py"
TIMEOUT = 10


def test_only_stdlib_imports():
    src = open(SCRIPT, encoding="utf-8").read()
    tree = ast.parse(src)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    third_party = {m for m in mods if m not in sys.stdlib_module_names}
    assert third_party == set(), "non-stdlib imports: %r" % (third_party,)


def test_runs_isolated_without_site_packages(tmp_path):
    inp = tmp_path / "in.csv"
    inp.write_bytes(b"email,name\nb@x.com,Bob\n")
    out = tmp_path / "out.csv"
    proc = subprocess.run(
        [sys.executable, "-I", "-S", SCRIPT, str(inp), str(out)],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"), newline=""))) == [["email", "name"], ["b@x.com", "Bob"]]
    assert inp.read_bytes() == b"email,name\nb@x.com,Bob\n"
