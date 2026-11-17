import ast
import os
import subprocess
import sys

APP = "/app"
SCRIPT = "/app/clean.py"
TIMEOUT = 10


def run(*args, cwd):
    return subprocess.run(
        [sys.executable, "-I", "-S", SCRIPT, *args],
        cwd=cwd,
        capture_output=True,
        timeout=TIMEOUT,
    )


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


def test_deliverable_is_clean_py(tmp_path):
    assert os.path.isfile(SCRIPT), "missing /app/clean.py"
    extra = sorted(p for p in os.listdir(APP) if p not in ("clean.py", "__pycache__"))
    assert extra == [], "unexpected extra deliverables in /app: %r" % extra
    inp = tmp_path / "in.csv"
    inp.write_bytes(b"email,name\nb@x.com,Bob\n")
    out = tmp_path / "out.csv"
    # -I -S: isolated mode, no site-packages, so third-party deps would fail
    proc = run(str(inp), str(out), cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert out.read_bytes() == b"email,name\nb@x.com,Bob\n"
