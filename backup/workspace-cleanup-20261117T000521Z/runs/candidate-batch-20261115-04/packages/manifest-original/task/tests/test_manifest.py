import hashlib
import json
import os
import subprocess
import sys
import tempfile
import shutil

import pytest

MANIFEST = "/app/src/manifest.py"
SRC_DIR = "/app/src"
TIMEOUT = 10


def run_manifest(input_dir, output_path):
    try:
        proc = subprocess.run(
            [sys.executable, MANIFEST, str(input_dir), str(output_path)],
            cwd="/",
            capture_output=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("manifest CLI timed out after %ss" % TIMEOUT)
    return proc


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def write_bytes(root, rel, data):
    full = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(data)
    return full


def snapshot(root):
    """Record full tree state: relative path -> (kind, content or None)."""
    root = str(root)
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            result[rel] = ("dir", None)
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as fh:
                result[rel] = ("file", fh.read())
    return result


def load_manifest(output_path):
    assert os.path.isfile(str(output_path)), "output JSON was not created"
    with open(str(output_path), "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        pytest.fail("output JSON is not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        pytest.fail("output is not valid JSON: %s" % exc)
    assert isinstance(data, list), "manifest must be a JSON array"
    for item in data:
        assert isinstance(item, dict), "each entry must be a JSON object"
        assert set(item.keys()) == {"path", "size", "sha256"}, (
            "entry must contain exactly path, size, sha256: %r" % (item,)
        )
        assert isinstance(item["path"], str)
        assert isinstance(item["size"], int) and not isinstance(item["size"], bool)
        assert isinstance(item["sha256"], str)
    paths = [item["path"] for item in data]
    assert paths == sorted(paths), "entries must be sorted by path string"
    return data


def expected_entries(spec):
    """spec: dict rel -> bytes; returns sorted list of dicts."""
    out = []
    for rel in sorted(spec):
        out.append({"path": rel, "size": len(spec[rel]), "sha256": sha256_of(spec[rel])})
    return out


@pytest.fixture()
def workdir():
    d = tempfile.mkdtemp(prefix="manifest_test_", dir="/tmp")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _build_and_check(workdir, spec):
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    for rel, data in spec.items():
        write_bytes(input_dir, rel, data)
    out = os.path.join(workdir, "manifest_out.json")
    before = snapshot(input_dir)
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "CLI failed: rc=%s stderr=%r" % (
        proc.returncode,
        proc.stderr,
    )
    after = snapshot(input_dir)
    assert after == before, "input directory tree was modified"
    entries = load_manifest(out)
    assert entries == expected_entries(spec)
    return entries


def test_exit_and_output_created(workdir):
    spec = {"a.txt": b"hello"}
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    write_bytes(input_dir, "a.txt", b"hello")
    out = os.path.join(workdir, "out.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    assert os.path.isfile(out), "output file not created"


def test_output_outside_input_dir(workdir):
    spec = {"x/y.txt": b"data"}
    input_dir = os.path.join(workdir, "deep")
    os.makedirs(input_dir)
    for rel, data in spec.items():
        write_bytes(input_dir, rel, data)
    out = os.path.join(workdir, "manifest.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    entries = load_manifest(out)
    assert entries == expected_entries(spec)


def test_empty_directory(workdir):
    entries = _build_and_check(workdir, {})
    assert entries == []


def test_only_empty_nested_dirs(workdir):
    input_dir = os.path.join(workdir, "input")
    os.makedirs(os.path.join(input_dir, "a", "b", "c"))
    os.makedirs(os.path.join(input_dir, "d"))
    out = os.path.join(workdir, "out.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    assert load_manifest(out) == []


def test_nested_paths(workdir):
    spec = {
        "top.txt": b"top",
        "a/inner.txt": b"inner",
        "a/b/c/d/e/leaf.txt": b"leaf",
        "a/b/deep.bin": b"\x00\x01\x02",
    }
    _build_and_check(workdir, spec)


def test_same_name_in_different_dirs(workdir):
    spec = {
        "readme.md": b"root readme",
        "assets/readme.md": b"assets readme",
        "assets/fonts/readme.md": b"fonts readme",
        "readme.txt": b"txt readme",
        "README.txt": b"upper readme",
    }
    _build_and_check(workdir, spec)


def test_spaces_and_unicode_names(workdir):
    spec = {
        "patch notes.txt": b"notes with space",
        "dir with space/inner file.dat": b"inner",
        "\u00dcberblick.md": "unicode content ä".encode("utf-8"),
        "deeper/\u4e2d\u6587\u76ee\u5f55/\u6587\u4ef6 \u540d.txt": b"chinese",
        "emoji\U0001F600.txt": b"emoji name",
        "quote\"name.txt": b"quote",
    }
    entries = _build_and_check(workdir, spec)
    paths = [e["path"] for e in entries]
    assert "dir with space/inner file.dat" in paths
    assert "deeper/\u4e2d\u6587\u76ee\u5f55/\u6587\u4ef6 \u540d.txt" in paths


def test_empty_file(workdir):
    spec = {"empty.bin": b"", "dir/also_empty.txt": b""}
    entries = _build_and_check(workdir, spec)
    by_path = {e["path"]: e for e in entries}
    assert by_path["empty.bin"]["size"] == 0
    assert by_path["empty.bin"]["sha256"] == sha256_of(b"")
    assert by_path["dir/also_empty.txt"]["size"] == 0


def test_binary_and_non_utf8_content(workdir):
    data = bytes(range(256)) + b"\xff\xfe\x80\x81\x00\x00"
    spec = {"binary.dat": data, "lf.txt": b"line1\nline2\n"}
    entries = _build_and_check(workdir, spec)
    by_path = {e["path"]: e for e in entries}
    assert by_path["binary.dat"]["size"] == len(data)
    assert by_path["binary.dat"]["sha256"] == sha256_of(data)


def test_sha256_lowercase_hex_len(workdir):
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    write_bytes(input_dir, "f.txt", b"abc")
    out = os.path.join(workdir, "out.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    entries = load_manifest(out)
    assert len(entries) == 1
    sha = entries[0]["sha256"]
    assert len(sha) == 64
    assert sha == sha.lower()
    assert all(c in "0123456789abcdef" for c in sha)
    assert sha == sha256_of(b"abc")


def test_stable_sorting_mixed(workdir):
    spec = {
        "b.txt": b"b",
        "a/z.txt": b"z",
        "a.txt": b"a",
        "B.txt": b"B",
        "a-a.txt": b"dash",
        "\u00e9.txt": "eacute".encode("utf-8"),
        "a/b.txt": b"ab",
    }
    entries = _build_and_check(workdir, spec)
    paths = [e["path"] for e in entries]
    assert paths == sorted(spec.keys())


def test_size_one_mib(workdir):
    data = bytes((i * 37) & 0xFF for i in range(1048576))
    spec = {"big.bin": data}
    entries = _build_and_check(workdir, spec)
    assert entries[0]["size"] == 1048576
    assert entries[0]["sha256"] == sha256_of(data)


def test_many_files_sorted(workdir):
    spec = {}
    for i in range(100):
        spec["f%03d.txt" % i] = ("file-%d" % i).encode()
    entries = _build_and_check(workdir, spec)
    assert len(entries) == 100
    assert [e["path"] for e in entries] == sorted(spec.keys())


def test_input_tree_unmodified(workdir):
    spec = {
        "keep.txt": b"keep",
        "sub/deeper/keep.bin": b"\x00\xff\x01",
        "\u00dcberblick.md": b"u",
    }
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    for rel, data in spec.items():
        write_bytes(input_dir, rel, data)
    os.makedirs(os.path.join(input_dir, "empty_dir", "nested"))
    before = snapshot(input_dir)
    out = os.path.join(workdir, "output.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    after = snapshot(input_dir)
    assert after == before


def test_no_output_written_inside_input(workdir):
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    write_bytes(input_dir, "a.txt", b"a")
    before = snapshot(input_dir)
    out = os.path.join(workdir, "out.json")
    proc = run_manifest(input_dir, out)
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    assert snapshot(input_dir) == before


def test_all_deliverable_modules_in_src():
    assert os.path.isdir(SRC_DIR), "/app/src must exist"
    assert os.path.isfile(MANIFEST), "/app/src/manifest.py must exist"


def test_runs_from_other_cwd(workdir):
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    write_bytes(input_dir, "x/y.txt", b"y")
    out = os.path.join(workdir, "out.json")
    proc = subprocess.run(
        [sys.executable, MANIFEST, input_dir, out],
        cwd=workdir,
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    entries = load_manifest(out)
    assert entries == expected_entries({"x/y.txt": b"y"})


def test_stdlib_only_import(workdir):
    """Run with site packages disabled to demonstrate stdlib-only operation."""
    input_dir = os.path.join(workdir, "input")
    os.makedirs(input_dir)
    write_bytes(input_dir, "a.txt", b"abc")
    out = os.path.join(workdir, "out.json")
    env = dict(os.environ)
    env["PYTHONNOUSERSITE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-S", MANIFEST, input_dir, out],
        cwd="/",
        capture_output=True,
        timeout=TIMEOUT,
        env=env,
    )
    assert proc.returncode == 0, "stderr=%r" % (proc.stderr,)
    entries = load_manifest(out)
    assert entries == expected_entries({"a.txt": b"abc"})
