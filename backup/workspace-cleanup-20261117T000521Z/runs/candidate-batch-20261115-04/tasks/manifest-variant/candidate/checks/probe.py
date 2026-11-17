import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

APP = "/app"
MANIFEST = "/app/src/manifest.py"
TIMEOUT = 10

REQUIREMENT_IDS = ("R1", "R2", "R3", "R4")

# (relative posix path, content bytes) for the main fixture tree.
MAIN_FILES = (
    ("a.txt", b"hello\n"),
    ("empty.bin", b""),
    ("empty-again.dat", b""),
    ("nul-content.bin", bytes(range(1, 8))),
    ("not-utf8.lat", b"\xff\xfe\x00binary \xc3\x28"),
    ("sub/a.txt", b"hello\n"),
    ("sub/deep/er/a.txt", b"other content\n"),
    ("sub/deep/er/b a.txt", b"hello\n"),
    ("sub/deep/er/with space.txt", b"\x00\x01\x02"),
    ("\u4e2d\u6587 \u6587\u4ef6.txt", b"hello\n"),
    ("\u00e9\u00e8\u00ea.bin", b"\x00\x01\x02"),
    ("deep/l1/l2/l3/l4/l5/l6/l7/last.bin", b"deep bytes"),
)

MAIN_DIRS = (
    "emptydir",
    "sub/emptydir",
    "deep/l1/l2/emptydir",
    "a-dir",
    "\u00fcn\u00efcode dir/nested empty",
)


def _snapshot(root):
    """Return {posix_rel_path: (is_dir, content_bytes_or_None)} for a tree."""
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir
        for name in dirnames:
            snap[os.path.join(rel_dir, name).replace(os.sep, "/")] = (True, None)
        for name in filenames:
            rel = os.path.join(rel_dir, name).replace(os.sep, "/")
            full = os.path.join(dirpath, name)
            with open(full, "rb") as fh:
                snap[rel] = (False, fh.read())
    return snap


def _mkdirs(root, rel):
    path = root
    for part in rel.split("/"):
        path = os.path.join(path, part)
        if not os.path.isdir(path):
            os.makedirs(path)


def _write_files(root, files, dirs):
    for rel in dirs:
        _mkdirs(root, rel)
    for rel, data in files:
        parts = rel.split("/")
        if len(parts) > 1:
            _mkdirs(root, "/".join(parts[:-1]))
        with open(os.path.join(root, *parts), "wb") as fh:
            fh.write(data)


def _make_tree(base):
    """Create a nested input tree and return (input_dir, output_path)."""
    inp = os.path.join(base, "input")
    os.makedirs(inp)
    _write_files(inp, MAIN_FILES, MAIN_DIRS)
    return inp, os.path.join(base, "output.json")


def _run(inp, out):
    return subprocess.run(
        [sys.executable, MANIFEST, inp, out],
        capture_output=True,
        timeout=TIMEOUT,
        cwd="/app",
    )


def _load(out):
    with open(out, "rb") as fh:
        raw = fh.read()
    return raw, json.loads(raw.decode("utf-8"))


def _expected(inp):
    groups = {}
    for dirpath, dirnames, filenames in os.walk(inp):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, inp).replace(os.sep, "/")
            with open(full, "rb") as fh:
                data = fh.read()
            groups.setdefault(hashlib.sha256(data).hexdigest(), []).append((rel, len(data)))
    entries = []
    for digest in sorted(groups):
        members = groups[digest]
        sizes = set(size for _, size in members)
        assert len(sizes) == 1
        entries.append({
            "size": sizes.pop(),
            "sha256": digest,
            "paths": sorted(rel for rel, _ in members),
        })
    return entries


def _check_output_shape(entries):
    hashes = []
    for entry in entries:
        assert isinstance(entry, dict), entry
        assert set(entry.keys()) == {"size", "sha256", "paths"}, entry
        assert isinstance(entry["size"], int) and not isinstance(entry["size"], bool)
        assert isinstance(entry["sha256"], str)
        assert len(entry["sha256"]) == 64
        assert entry["sha256"] == entry["sha256"].lower()
        int(entry["sha256"], 16)
        hashes.append(entry["sha256"])
        assert isinstance(entry["paths"], list) and entry["paths"]
        assert entry["paths"] == sorted(entry["paths"]), entry
        assert all(isinstance(p, str) and "\\" not in p for p in entry["paths"])
    assert hashes == sorted(hashes)
    assert len(set(hashes)) == len(hashes)


def _case_r1():
    base = tempfile.mkdtemp(prefix="probe-r1-", dir="/tmp")
    try:
        inp, out = _make_tree(base)
        proc = _run(inp, out)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        assert os.path.isfile(out), "output file missing"
        _, entries = _load(out)
        assert isinstance(entries, list)
        assert entries, "expected non-empty manifest"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _case_r2():
    base = tempfile.mkdtemp(prefix="probe-r2-", dir="/tmp")
    try:
        inp, out = _make_tree(base)
        proc = _run(inp, out)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        _, entries = _load(out)
        _check_output_shape(entries)
        expected = _expected(inp)
        assert entries == expected, (entries, expected)
        all_paths = [p for e in entries for p in e["paths"]]
        for wanted in ("sub/a.txt", "a.txt", "sub/deep/er/a.txt", "sub/deep/er/b a.txt",
                       "\u4e2d\u6587 \u6587\u4ef6.txt",
                       "deep/l1/l2/l3/l4/l5/l6/l7/last.bin"):
            assert wanted in all_paths, wanted
        assert len(all_paths) == len(MAIN_FILES), all_paths
        assert not any("emptydir" in p for p in all_paths), all_paths
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _case_r3():
    base = tempfile.mkdtemp(prefix="probe-r3-", dir="/tmp")
    try:
        empty_dir = os.path.join(base, "empty")
        _mkdirs(empty_dir, "x/y")
        out = os.path.join(base, "out.json")
        proc = _run(empty_dir, out)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        _, entries = _load(out)
        assert entries == [], entries

        inp, out = _make_tree(base)
        proc = _run(inp, out)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        _, entries = _load(out)
        _check_output_shape(entries)
        by_hash = {}
        for entry in entries:
            by_hash[entry["sha256"]] = entry

        hello = hashlib.sha256(b"hello\n").hexdigest()
        text_group = by_hash[hello]
        assert text_group["size"] == 6, text_group
        assert text_group["paths"] == sorted(
            ["a.txt", "sub/a.txt", "sub/deep/er/b a.txt", "\u4e2d\u6587 \u6587\u4ef6.txt"]
        ), text_group

        empty = hashlib.sha256(b"").hexdigest()
        assert by_hash[empty]["size"] == 0, by_hash[empty]
        assert by_hash[empty]["paths"] == ["empty-again.dat", "empty.bin"]

        binary = hashlib.sha256(b"\x00\x01\x02").hexdigest()
        assert set(by_hash[binary]["paths"]) == set([
            "sub/deep/er/with space.txt", "\u00e9\u00e8\u00ea.bin"
        ]), by_hash[binary]
        assert by_hash[binary]["size"] == 3

        assert entries == _expected(inp)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _case_r4():
    base = tempfile.mkdtemp(prefix="probe-r4-", dir="/tmp")
    try:
        inp, out = _make_tree(base)
        before = _snapshot(inp)
        proc = _run(inp, out)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        after = _snapshot(inp)
        assert before == after, "input tree modified"
        assert os.path.isfile(out)

        src = os.path.join(APP, "src")
        assert os.path.isdir(src), "missing /app/src"

        alt_out = os.path.join(base, "isolated.json")
        proc = subprocess.run(
            [sys.executable, "-I", MANIFEST, inp, alt_out],
            capture_output=True, timeout=TIMEOUT, cwd="/tmp",
        )
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        _, entries = _load(alt_out)
        assert entries == _expected(inp)

        proc = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys; sys.path.insert(0, '/app/src'); import manifest"],
            capture_output=True, timeout=TIMEOUT, cwd="/tmp",
        )
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    finally:
        shutil.rmtree(base, ignore_errors=True)


_CASES = {
    "R1": _case_r1,
    "R2": _case_r2,
    "R3": _case_r3,
    "R4": _case_r4,
}


def check(requirement_id):
    if requirement_id not in _CASES:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    _CASES[requirement_id]()
