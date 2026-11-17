"""Behavioral probe for the customer CSV cleaning task.

Each requirement is checked against the actual CLI behaviour in /app.
All temporary fixtures live under /tmp; /app content is never modified.
"""

import csv
import io
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
SCRIPT = os.path.join(APP, "clean.py")
DEFAULT_CSV = os.path.join(APP, "customers.csv")


def _run(input_path, output_path):
    return subprocess.run(
        [sys.executable, SCRIPT, input_path, output_path],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _parse_csv_text(text):
    """Return (header, rows) parsed with the standard CSV rules."""
    reader = csv.reader(io.StringIO(text))
    records = [row for row in reader if row]
    if not records:
        return None, []
    return records[0], records[1:]


def _normalize(email, name):
    return (email.strip().lower(), name.strip())


def _expected(header, rows, strict=True):
    """Apply the spec: dedupe by normalised email, keep first name/order."""
    seen = set()
    out = []
    for row in rows:
        if not row:
            continue
        email = row[0] if row else ""
        name = row[1] if len(row) > 1 else ""
        key, cleaned_name = _normalize(email, name)
        if key in seen:
            continue
        seen.add(key)
        out.append([key, cleaned_name])
    return out


def _write_fixture(dirpath, name, content):
    path = os.path.join(dirpath, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return path


def _output_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    assert text.startswith("email,name"), (
        "output must start with the exact header 'email,name', got %r" % (text[:40],)
    )
    return text


def _check_case(header, body, expect_rows, label):
    """Run one fixture through the CLI and compare with expected rows."""
    tmp = tempfile.mkdtemp(prefix="probe-clean-", dir="/tmp")
    try:
        content = header + body
        src = _write_fixture(tmp, "in.csv", content)
        dst = os.path.join(tmp, "out.csv")
        before = hashlib.sha256(content.encode("utf-8")).hexdigest()
        proc = _run(src, dst)
        assert proc.returncode == 0, (
            "%s: expected exit code 0, got %r (stderr=%r)"
            % (label, proc.returncode, proc.stderr[-500:])
        )
        assert os.path.exists(dst), "%s: output file was not created" % label
        text = _output_text(dst)
        got_header, got_rows = _parse_csv_text(text)
        assert got_header == ["email", "name"], (
            "%s: expected header ['email', 'name'], got %r" % (label, got_header)
        )
        expected = [[e, n] for e, n in expect_rows]
        assert got_rows == expected, (
            "%s: expected rows %r, got %r" % (label, expected, got_rows)
        )
        with open(src, "rb") as fh:
            after = hashlib.sha256(fh.read()).hexdigest()
        assert before == after, "%s: input file was modified" % label
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _spec_rows(rows):
    seen = set()
    out = []
    for email, name in rows:
        key, cleaned = _normalize(email, name)
        if key in seen:
            continue
        seen.add(key)
        out.append([key, cleaned])
    return out


def check_r1():
    # Two positional args, exit 0, well-formed CSV written from realistic data.
    rows = [
        ("alice@example.com", "Alice"),
        ("bob@example.com", "Bob"),
    ]
    body = "".join("%s,%s\n" % r for r in rows)
    tmp = tempfile.mkdtemp(prefix="probe-r1-", dir="/tmp")
    try:
        src = _write_fixture(tmp, "in.csv", "email,name\n" + body)
        dst = os.path.join(tmp, "out.csv")
        proc = _run(src, dst)
        assert proc.returncode == 0, (
            "expected exit code 0, got %r (stderr=%r)"
            % (proc.returncode, proc.stderr[-500:])
        )
        assert os.path.exists(dst), "output file was not created"
        text = _output_text(dst)
        header, out_rows = _parse_csv_text(text)
        assert header == ["email", "name"], "unexpected header %r" % (header,)
        assert out_rows == [[e, n] for e, n in rows], (
            "expected %r, got %r" % ([[e, n] for e, n in rows], out_rows)
        )
        # Trailing newline convention: one record per line, no stray blank rows.
        lines = [ln for ln in text.split("\n") if ln != ""]
        assert len(lines) == len(out_rows) + 1, (
            "expected %d non-empty lines, got %d" % (len(out_rows) + 1, len(lines))
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_r2():
    # Whitespace, case folding, quoted names containing commas, duplicates.
    header = "email,name\n"
    body = (
        '  Alice@Example.COM  ,Alice Chen\n'
        '"bob@example.com","Bob, Jr."\n'
        "alice@example.com,Duplicate Alice\n"
        '  BOB@EXAMPLE.COM ,"  Bob Lin  "\n'
        'carol@example.com,"Carol ""CJ"" Wu"\n'
        "  Carol@Example.com ,Second Carol\n"
    )
    expected = _spec_rows(
        [
            ("  Alice@Example.COM  ", "Alice Chen"),
            ("bob@example.com", "Bob, Jr."),
            ("alice@example.com", "Duplicate Alice"),
            ("  BOB@EXAMPLE.COM ", "  Bob Lin  "),
            ("carol@example.com", 'Carol "CJ" Wu'),
            ("  Carol@Example.com ", "Second Carol"),
        ]
    )
    _check_case(header, body, expected, "R2 core")


def check_r3():
    # Header-only input.
    _check_case("email,name\n", "", [], "R3 header-only")
    # Header-only with CRLF endings and non-example data.
    _check_case("email,name\r\n", "", [], "R3 header-only CRLF")
    # Boundary: 1000 records built from duplicates of a few emails.
    rows = []
    for i in range(1000):
        base = ["Zed@Example.org", "amy@example.net", "kim@example.io"][i % 3]
        pad = " " * (i % 3)
        rows.append((pad + base.upper() + pad, "Name %d" % i))
    body = "".join(
        ('"%s","%s"\n' % (e, n)) for e, n in rows
    )
    expected = _spec_rows(rows)
    assert len(expected) == 3, "fixture sanity check failed"
    _check_case("email,name\n", body, expected, "R3 1000 rows")
    # Different valid data, unordered emails with mixed case, single record.
    _check_case(
        "email,name\n",
        "only@one.test,Only One\n",
        [["only@one.test", "Only One"]],
        "R3 single record",
    )
    _check_case(
        "email,name\n",
        "zz@z.test,Last\nAa@a.test,First\n",
        [["zz@z.test", "Last"], ["aa@a.test", "First"]],
        "R3 order preserved",
    )


def check_r4():
    # Input not modified; no non-stdlib imports; bundled sample file still clean.
    tmp = tempfile.mkdtemp(prefix="probe-r4-", dir="/tmp")
    try:
        content = (
            "email,name\n"
            "  Alice@Example.COM  ,Alice Chen\n"
            "alice@example.com,Alice Again\n"
            'bob@example.com,"Bob, Jr."\n'
        )
        src = _write_fixture(tmp, "in.csv", content)
        with open(src, "rb") as fh:
            digest_before = hashlib.sha256(fh.read()).hexdigest()
        mtime_before = os.stat(src).st_mtime_ns
        dst = os.path.join(tmp, "nested_out.csv")
        proc = _run(src, dst)
        assert proc.returncode == 0, "expected exit 0, got %r (stderr=%r)" % (
            proc.returncode,
            proc.stderr[-500:],
        )
        with open(src, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == digest_before, (
                "input file content was modified"
            )
        assert os.stat(src).st_mtime_ns == mtime_before, (
            "input file was rewritten"
        )

        # Only declared deliverables: clean.py must exist with no pyc leftovers.
        assert os.path.exists(SCRIPT), "/app/clean.py is missing"
        assert not os.path.exists(os.path.join(APP, "clean.pyc")), (
            "stray clean.pyc in /app"
        )

        # Import graph must stay within the standard library.
        probe_code = (
            "import importlib.util, sys, os\n"
            "sys.dont_write_bytecode = True\n"
            "spec = importlib.util.spec_from_file_location('clean_probe', %r)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "names = set()\n"
            "for v in vars(mod).values():\n"
            "    m = getattr(v, '__module__', None)\n"
            "    if isinstance(v, type(sys)) and m:\n"
            "        names.add(m)\n"
            "print('\\n'.join(sorted(names)))\n" % SCRIPT
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe_code],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        assert proc.returncode == 0, (
            "could not import clean.py: %r" % (proc.stderr[-500:],)
        )
        mods = [m for m in proc.stdout.split("\n") if m.strip()]
        allowed = set(sys.stdlib_module_names) | {"clean_probe"}
        bad = [m for m in mods if m not in allowed]
        assert not bad, "non-stdlib modules imported: %r" % (bad,)

        # A valid output for the same non-example data (behaviour still correct).
        text = _output_text(dst)
        _, got_rows = _parse_csv_text(text)
        assert got_rows == [
            ["alice@example.com", "Alice Chen"],
            ["bob@example.com", "Bob, Jr."],
        ], "unexpected rows %r" % (got_rows,)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CHECKS = {
    "R1": check_r1,
    "R2": check_r2,
    "R3": check_r3,
    "R4": check_r4,
}


def check(requirement_id):
    if requirement_id not in CHECKS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    CHECKS[requirement_id]()
