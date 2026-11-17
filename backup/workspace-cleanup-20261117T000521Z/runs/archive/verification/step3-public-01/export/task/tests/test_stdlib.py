import os
import subprocess
import sys
import tempfile

APP = "/app/clean.py"
TIMEOUT = 10


def test_script_works_with_only_stdlib_importable():
    """Run isolated with site-packages disabled: no third-party dependency allowed."""
    d = tempfile.mkdtemp(prefix="clean_iso_", dir="/tmp")
    inp = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(inp, "w", encoding="utf-8", newline="") as fh:
        fh.write("email,name\n a@b.c ,N\n A@B.C ,M\n")
    proc = subprocess.run(
        [sys.executable, "-I", "-S", APP, inp, out],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, (
        "script failed with only the standard library importable; "
        "stderr: %s" % proc.stderr
    )
    with open(out, "r", encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines()
    assert lines[0] == "email,name"
    assert lines[1:] == ["a@b.c,N"]


def test_no_install_or_dependency_artifacts_in_app():
    entries = set(os.listdir("/app"))
    assert "clean.py" in entries, "clean.py is missing from /app"
    forbidden = {
        "sitecustomize.py",
        "usercustomize.py",
        "conftest.py",
        "setup.py",
        "requirements.txt",
        "Pipfile",
        "pyproject.toml",
    }
    assert not (entries & forbidden), (
        "unexpected install/hook files in /app: %r" % sorted(entries & forbidden)
    )
