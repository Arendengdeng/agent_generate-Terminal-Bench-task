"""Behavioral probe for the customer CSV cleaning repair task."""

import csv
import io
import os
import subprocess
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"

REQUIREMENT_IDS = ("R1", "R2", "R3", "R4")

STDLIB_OK = {
    "csv",
    "sys",
    "os",
    "io",
    "argparse",
    "codecs",
    "re",
    "collections",
    "itertools",
    "typing",
    "math",
    "string",
}


def _snapshot(path):
    st = os.stat(path)
    with open(path, "rb") as fh:
        return (fh.read(), st.st_mode)


def _run(input_text, name="in.csv"):
    tmpdir = tempfile.mkdtemp(prefix="probe_", dir="/tmp")
    src = os.path.join(tmpdir, name)
    dst = os.path.join(tmpdir, "out.csv")
    with open(src, "wb") as fh:
        fh.write(input_text.encode("utf-8"))
    before = _snapshot(src)
    proc = subprocess.run(
        ["python", os.path.join(APP, "clean.py"), src, dst],
        timeout=COMMAND_TIMEOUT_SEC,
        capture_output=True,
    )
    after = _snapshot(src)
    out = None
    if os.path.exists(dst):
        with open(dst, "rb") as fh:
            out = fh.read().decode("utf-8")
    return proc, out, before, after


def _parse(text):
    rows = list(csv.reader(io.StringIO(text)))
    assert rows, "output is empty"
    return rows[0], rows[1:]


def _expect(input_text, expected_rows):
    proc, out, before, after = _run(input_text)
    assert proc.returncode == 0, (
        "non-zero exit: %r stderr=%r" % (proc.returncode, proc.stderr)
    )
    assert out is not None, "output file was not written"
    header, rows = _parse(out)
    assert header == ["email", "name"], "wrong header: %r" % (header,)
    assert rows == expected_rows, "wrong rows: %r != %r" % (rows, expected_rows)
    assert before == after, "input file was modified"


def check(requirement_id):
    if requirement_id not in REQUIREMENT_IDS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))

    if requirement_id == "R1":
        proc, out, before, after = _run(
            "email,name\n Foo@Bar.COM , Foo Bar \n"
        )
        assert proc.returncode == 0, "non-zero exit: %r" % (proc.returncode,)
        assert out is not None, "output file was not written"
        lines = [l for l in out.splitlines() if l.strip()]
        assert lines and lines[0] == "email,name", "wrong header line: %r" % (lines[:1],)
        header, rows = _parse(out)
        assert header == ["email", "name"], "wrong header: %r" % (header,)
        assert rows == [["foo@bar.com", "Foo Bar"]], "wrong rows: %r" % (rows,)


    elif requirement_id == "R2":
        text = (
            "email,name\n"
            "  Alice@Example.com  , Alice Wong\n"
            "bob@example.com,Bob Li\n"
            "alice@example.com,\"Smith, Alice\"\n"
            " BOB@EXAMPLE.COM ,  Bob Second \n"
            "carol@example.com ,\"Carol, C.\"\n"
            "dave@example.com,\"Dave \"\"The\"\" Man\"\n"
            "\n"
            "erin@example.com,  Erin  Lee  \n"
        )
        _expect(
            text,
            [
                ["alice@example.com", "Alice Wong"],
                ["bob@example.com", "Bob Li"],
                ["carol@example.com", "Carol, C."],
                ["dave@example.com", 'Dave "The" Man'],
                ["erin@example.com", "Erin  Lee"],
            ],
        )

    elif requirement_id == "R3":
        proc, out, before, after = _run("email,name\n")
        assert proc.returncode == 0, "header-only input failed: %r" % (proc.stderr,)
        assert out is not None, "no output for header-only input"
        header, rows = _parse(out)
        assert header == ["email", "name"], "wrong header for header-only: %r" % (header,)
        assert rows == [], "expected no data rows, got %r" % (rows,)
        assert before == after, "input modified for header-only case"

        _expect(
            "email,name\n"
            "Zed@Corp.io ,\"Zed, Jr.\"\n"
            "zed@corp.io,Dup\n"
            "  AMY@corp.io, Amy \n",
            [["zed@corp.io", "Zed, Jr."], ["amy@corp.io", "Amy"]],
        )

        lines = ["email,name"]
        expected = []
        seen = set()
        for i in range(1000):
            key = "user%d@example.com" % (i % 400)
            raw = key.upper() if i % 3 == 0 else key
            lines.append(' %s , "Name %d, x"\n' % (raw, i))
            if key not in seen:
                seen.add(key)
                expected.append([key, "Name %d, x" % i])
        _expect("".join(lines), expected)

        _expect(
            "email,name\nnoname@example.com,\nnoname@example.com,Filled\n",
            [["noname@example.com", ""]],
        )

    elif requirement_id == "R4":
        proc, out, before, after = _run("email,name\na@b.com,Dup\na@b.com,X\n")
        assert proc.returncode == 0, "run failed: %r" % (proc.stderr,)
        assert before == after, "input file content or mode was modified"

        src_path = os.path.join(APP, "clean.py")
        assert os.path.isfile(src_path), "clean.py missing"
        with open(src_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        for line in source.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                mod = s.split()[1].split(".")[0]
                assert mod in STDLIB_OK, "non-stdlib import: %r" % (s,)

        tmpdir = tempfile.mkdtemp(prefix="probe_cwd_", dir="/tmp")
        src = os.path.join(tmpdir, "i.csv")
        dst = os.path.join(tmpdir, "o.csv")
        with open(src, "w", encoding="utf-8", newline="") as fh:
            fh.write("email,name\nB@C.com, Bee \n")
        before = _snapshot(src)
        proc = subprocess.run(
            ["python", src_path, src, dst],
            timeout=COMMAND_TIMEOUT_SEC,
            capture_output=True,
            cwd=tmpdir,
        )
        after = _snapshot(src)
        assert proc.returncode == 0, "run from other cwd failed: %r" % (proc.stderr,)
        assert before == after, "input modified when run from other cwd"
        with open(dst, "r", encoding="utf-8", newline="") as fh:
            header, rows = _parse(fh.read())
        assert header == ["email", "name"], "wrong header"
        assert rows == [["b@c.com", "Bee"]], "wrong rows: %r" % (rows,)
    else:  # pragma: no cover
        raise ValueError(requirement_id)


if __name__ == "__main__":
    for rid in REQUIREMENT_IDS:
        check(rid)
        print(rid, "ok")
