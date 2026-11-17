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
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TIMEOUT = 10


def run_clean(input_path, output_path):
    return subprocess.run(
        [sys.executable, CLEAN, input_path, output_path],
        cwd=tempfile.gettempdir(),
        capture_output=True,
        timeout=TIMEOUT,
    )


def read_output(path):
    assert os.path.isfile(path), "expected output CSV was not written"
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def expected_from_rows(rows):
    seen = set()
    out = []
    for email, name in rows:
        norm = email.strip().lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append([norm, name.strip()])
    return out


def expected_from_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["email", "name"]
    return expected_from_rows(rows[1:])


@pytest.fixture
def workdir():
    d = tempfile.mkdtemp(prefix="clean-test-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def copy_fixture(name, workdir):
    dst = os.path.join(workdir, "input.csv")
    shutil.copyfile(os.path.join(FIXTURES, name), dst)
    return dst


def write_input(workdir, text):
    path = os.path.join(workdir, "input.csv")
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


# ---------- R1: CLI contract and canonical output ----------

def test_cli_success_exit_zero_and_header(workdir):
    src = copy_fixture("small.csv", workdir)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == expected_from_fixture("small.csv")
    assert len(data) == 4


def test_cli_canonical_csv_roundtrip_quoting(workdir):
    src = write_input(
        workdir,
        'email,name\r\n'
        'x@example.com,"Name, With Comma"\r\n'
        'y@example.com,"Quote "" Inside"\r\n'
    )
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == [
        ["x@example.com", "Name, With Comma"],
        ["y@example.com", 'Quote " Inside'],
    ]


def test_cli_output_written_to_second_argument(workdir):
    src = copy_fixture("header_only.csv", workdir)
    out = os.path.join(workdir, "custom_out.csv")
    proc = run_clean(src, out)
    check_result(proc, out)


# ---------- R2: normalization, stable dedup, quoting ----------

def test_quoted_commas_and_dedup_first_name(workdir):
    src = copy_fixture("quoted_commas.csv", workdir)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    expected = expected_from_fixture("quoted_commas.csv")
    assert data[1:] == expected
    assert expected == [
        ["alice@example.com", "Alice Chen"],
        ["bob+tag@example.com", "Lin, Bob"],
        ["carol@example.com", 'Wu, "CJ", Carol'],
        ["dave@example.com", "Dave Smith"],
    ]


def test_case_and_whitespace_dedup(workdir):
    src = copy_fixture("case_whitespace.csv", workdir)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    expected = expected_from_fixture("case_whitespace.csv")
    assert data[1:] == expected
    assert expected == [
        ["a@x.com", "First A"],
        ["b@x.com", "Spaced B"],
        ["c@x.com", "Inner  Double  Space"],
        ["e@x.com", "Trailing space, quoted"],
        ["f@x.com", "leading quoted"],
    ]


def test_stable_order_preserved_across_many_duplicates(workdir):
    raw = [("email", "name")]
    records = [
        ("  Zed@Mail.COM ", "  Zed First  "),
        ("amy@mail.com", "Amy"),
        ("ZED@mail.com", "Zed Second"),
        ("bob@mail.com", 'Robert, "Bobby"'),
        ("amy@MAIL.com", "Amy Later"),
        ("carl@mail.com", "Carl"),
        ("BOB@mail.com", "Bob Dup"),
    ]
    raw.extend(records)
    with open(os.path.join(workdir, "input.csv"), "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(raw)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(os.path.join(workdir, "input.csv"), out)
    data = check_result(proc, out)
    assert data[1:] == [
        ["zed@mail.com", "Zed First"],
        ["amy@mail.com", "Amy"],
        ["bob@mail.com", 'Robert, "Bobby"'],
        ["carl@mail.com", "Carl"],
    ]


def test_name_inner_whitespace_preserved(workdir):
    src = write_input(
        workdir,
        'email,name\n'
        'p@q.com,  Anna  Maria  Lee  \n'
        'r@q.com,"  tab\there  "\n'
    )
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert data[1:] == [
        ["p@q.com", "Anna  Maria  Lee"],
        ["r@q.com", "tab\there"],
    ]


# ---------- R3: header-only, varied valid inputs, no hardcoding ----------

def test_header_only_input_gives_header_only_output(workdir):
    src = copy_fixture("header_only.csv", workdir)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    data = check_result(proc, out)
    assert len(data) == 1, "expected header-only output, got %r" % (data,)


def test_varied_generated_inputs_match_spec(workdir):
    cases = [
        [("A@B.com", "Alpha")],
        [("a@b.com", "one"), ("a@b.com", "two"), ("a@b.com", "three")],
        [("q@q.com", "x, y"), ("w@w.com", 'he said "hi"')],
        [("  Mix@Case.Com  ", "  spaced  "), ("mix@case.com", "later")],
        [("z@z.com", "Z"), ("y@y.com", "Y"), ("Z@Z.com", "Z dup")],
    ]
    for i, records in enumerate(cases):
        sub = os.path.join(workdir, "case%d" % i)
        os.makedirs(sub)
        with open(os.path.join(sub, "in.csv"), "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([("email", "name")] + records)
        out = os.path.join(sub, "out.csv")
        proc = run_clean(os.path.join(sub, "in.csv"), out)
        data = check_result(proc, out)
        assert data[1:] == expected_from_rows(records), "case %d failed" % i


def test_large_input_up_to_limit(workdir):
    base = os.path.join(workdir, "input.csv")
    records = []
    for i in range(1000):
        records.append(("user%d@example.com" % (i % 400), "  Name %d  " % i))
    with open(base, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([("email", "name")] + records)
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(base, out)
    data = check_result(proc, out)
    expected = expected_from_rows(records)
    assert len(expected) == 400
    assert data[1:] == expected


# ---------- R4: input untouched, clean.py stdlib only ----------

def test_input_file_not_modified(workdir):
    src = copy_fixture("quoted_commas.csv", workdir)
    with open(src, "rb") as fh:
        before = hashlib.sha256(fh.read()).hexdigest()
    out = os.path.join(workdir, "out.csv")
    proc = run_clean(src, out)
    check_result(proc, out)
    with open(src, "rb") as fh:
        after = hashlib.sha256(fh.read()).hexdigest()
    assert before == after, "input file was modified"


def test_clean_py_imports_stdlib_only():
    import ast

    assert os.path.isfile(CLEAN), "/app/clean.py missing"
    with open(CLEAN, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in stdlib, "non-stdlib import: %s" % alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            top = (node.module or "").split(".")[0]
            assert top in stdlib, "non-stdlib import: %s" % (node.module,)


def test_runs_without_third_party_site_packages(workdir):
    src = copy_fixture("case_whitespace.csv", workdir)
    out = os.path.join(workdir, "out.csv")
    env = dict(os.environ)
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        [sys.executable, "-S", CLEAN, src, out],
        cwd=tempfile.gettempdir(),
        capture_output=True,
        timeout=TIMEOUT,
        env=env,
    )
    check_result(proc, out)
