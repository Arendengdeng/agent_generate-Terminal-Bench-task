import csv
import io
import os
import shutil
import subprocess
import tempfile

APP_DIR = "/app"
SCRIPT = os.path.join(APP_DIR, "clean.py")
COMMAND_TIMEOUT_SEC = 10


def _run(inp_path, out_path):
    return subprocess.run(
        ["python", SCRIPT, inp_path, out_path],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _parse_output(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    rows = [r for r in csv.reader(io.StringIO(raw)) if r]
    return rows


def _write_input(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _do_case(header_text, expected):
    """Run one fixture, assert exit code 0, header exactly email,name and rows == expected."""
    tmp = tempfile.mkdtemp(prefix="cleanprobe_", dir="/tmp")
    try:
        inp = os.path.join(tmp, "in.csv")
        out = os.path.join(tmp, "out.csv")
        _write_input(inp, header_text)
        proc = _run(inp, out)
        assert proc.returncode == 0, (
            "expected exit 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
        )
        assert os.path.exists(out), "output file was not created"
        rows = _parse_output(out)
        assert rows, "output is empty, expected a header row"
        assert rows[0] == ["email", "name"], "bad output header: %r" % (rows[0],)
        got = [tuple(r) for r in rows[1:]]
        exp = [tuple(r) for r in expected]
        assert got == exp, "rows mismatch: got %r expected %r" % (got, exp)
        return tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_complex():
    # quoted fields with commas, whitespace, mixed case, duplicates, order.
    data = (
        'email,name\n'
        'alice@example.com,Alice Chen\n'
        ' bob@example.com ,Bob Li\n'
        '"carol@example.com","Carol, Jr."\n'
        'ALICE@Example.COM,Alicia Chen\n'
        '"dave@example.com "," Dave, Sr. "\n'
        'Bob@Example.com,Robert Li\n'
        '  Carol@Example.com  ,"Carol, Jr. (dup)"\n'
        'eve@example.com,"Eve ""Evie"" Park"\n'
        'EVE@example.com,Eve Second\n'
    )
    expected = [
        ["alice@example.com", "Alice Chen"],
        ["bob@example.com", "Bob Li"],
        ["carol@example.com", "Carol, Jr."],
        ["dave@example.com", "Dave, Sr."],
        ["eve@example.com", 'Eve "Evie" Park'],
    ]
    _do_case(data, expected)


def check(requirement_id):
    if requirement_id == "R1":
        tmp = tempfile.mkdtemp(prefix="cleanprobe_", dir="/tmp")
        try:
            inp = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            _write_input(inp, "email,name\nx@example.com,X Y\n")
            proc = _run(inp, out)
            assert proc.returncode == 0, (
                "expected exit 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
            )
            rows = _parse_output(out)
            assert rows == [["email", "name"], ["x@example.com", "X Y"]], (
                "unexpected output rows: %r" % (rows,)
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif requirement_id == "R2":
        _check_complex()
        # names are trimmed at both ends, inner whitespace and case preserved
        tmp = tempfile.mkdtemp(prefix="cleanprobe_", dir="/tmp")
        try:
            inp = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            _write_input(
                inp,
                "email,name\n"
                '\tMiXed@Example.COM \t ,"  Jane  Ann  "\n'
                'mixed@example.com,Jane Clone\n',
            )
            proc = _run(inp, out)
            assert proc.returncode == 0, (
                "expected exit 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
            )
            rows = _parse_output(out)
            assert rows == [["email", "name"], ["mixed@example.com", "Jane  Ann"]], (
                "unexpected output rows: %r" % (rows,)
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif requirement_id == "R3":
        # header-only input
        _do_case("email,name\n", [])
        # no trailing newline on record
        _do_case("email,name\nsolo@example.com,Solo Person", [["solo@example.com", "Solo Person"]])
        # different legal data, no relation to sample
        _do_case(
            "email,name\n"
            'zzz@example.org,"Zed, Zulu"\n'
            'aaa@example.org,Alpha Order\n'
            'ZZZ@EXAMPLE.ORG,Again\n',
            [["zzz@example.org", "Zed, Zulu"], ["aaa@example.org", "Alpha Order"]],
        )
        # sample file contents must be handled by rules, not hardcoded
        _do_case(
            "email,name\n"
            'k1@example.net,"K, One"\n'
            ' K2@Example.NET ," K Two "\n'
            'k1@EXAMPLE.net,dup\n'
            'k3@example.net,"Name, With, Commas"\n',
            [
                ["k1@example.net", "K, One"],
                ["k2@example.net", "K Two"],
                ["k3@example.net", "Name, With, Commas"],
            ],
        )
        # many records: all duplicate emails collapse to first, order stable
        lines = ["email,name"]
        expected = []
        for i in range(200):
            lines.append("user%d@example.com,Name %d" % (i, i))
            expected.append(["user%d@example.com" % i, "Name %d" % i])
        lines.append("USER0@EXAMPLE.COM,dup first")
        lines.append(" user199@example.com ,dup last")
        _do_case("\n".join(lines) + "\n", expected)
    elif requirement_id == "R4":
        for p in ("/app/clean.py",):
            assert os.path.isfile(p), "missing deliverable %s" % p
        with open(SCRIPT, "r", encoding="utf-8") as fh:
            src = fh.read()
        allowed = set(["csv", "sys", "io", "os", "argparse", "re", "unicodedata", "codecs", "pathlib", "__future__"])
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top in allowed, "non-stdlib/unexpected import: %s" % alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                top = (node.module or "").split(".")[0]
                assert top in allowed, "non-stdlib/unexpected import: %s" % node.module
        # input file untouched, additional files not required
        tmp = tempfile.mkdtemp(prefix="cleanprobe_", dir="/tmp")
        try:
            inp = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            content = 'email,name\nA@Example.com,"A, One"\n a@example.com ,A Two\n'
            _write_input(inp, content)
            before = os.stat(inp).st_mtime_ns
            with open(inp, "rb") as fh:
                before_bytes = fh.read()
            proc = _run(inp, out)
            assert proc.returncode == 0, (
                "expected exit 0, got %r; stderr=%r" % (proc.returncode, proc.stderr)
            )
            with open(inp, "rb") as fh:
                assert fh.read() == before_bytes, "input file was modified"
            assert os.stat(inp).st_mtime_ns == before, "input file mtime changed"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
