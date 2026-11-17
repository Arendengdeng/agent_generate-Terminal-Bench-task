"""Behavioral probe for the directory manifest CLI repair task."""

import hashlib
import json
import os
import subprocess
import tempfile

COMMAND_TIMEOUT_SEC = 10
CLI = "/app/src/manifest.py"

REQUIREMENTS = ("R1", "R2", "R3", "R4")


# ---------------------------------------------------------------- helpers


def _build(root, files):
    """Create files given as {relative posix path: bytes} below root."""
    for rel, data in files.items():
        full = os.path.join(root, *rel.split("/"))
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)


def _snapshot(root):
    """Describe the whole input tree (dirs, files, mtimes, contents)."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        state[("dir", rel_dir)] = tuple(sorted(dirnames))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                state[("link", rel)] = os.readlink(full)
                continue
            st = os.stat(full)
            with open(full, "rb") as fh:
                data = fh.read()
            state[("file", rel)] = (st.st_size, st.st_mtime_ns, data)
    return state


def _run(root, out_path):
    return subprocess.run(
        ["python", CLI, root, out_path],
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )


def _run_manifest(files, dirs=()):
    """Build a fixture, run the CLI, return (proc, raw output, payload)."""
    work = tempfile.mkdtemp(prefix="manifest-probe-", dir="/tmp")
    root = os.path.join(work, "input")
    os.makedirs(root)
    for d in dirs:
        os.makedirs(os.path.join(root, *d.split("/")), exist_ok=True)
    _build(root, files)
    out_path = os.path.join(work, "manifest.json")
    proc = _run(root, out_path)
    raw = None
    payload = None
    if os.path.exists(out_path):
        with open(out_path, "rb") as fh:
            raw = fh.read()
    if raw is not None:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = None
    return proc, raw, payload


def _expect_ok(proc, payload):
    assert proc.returncode == 0, (
        "CLI exit %r stderr=%r" % (proc.returncode, proc.stderr[-800:])
    )
    assert payload is not None, "output is not a UTF-8 JSON document"
    assert isinstance(payload, list), "output root is not a JSON array"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _expected(files):
    return [
        {"path": rel, "size": len(data), "sha256": _sha(data)}
        for rel, data in sorted(files.items(), key=lambda kv: kv[0])
    ]


def _check_shape(payload):
    for item in payload:
        assert isinstance(item, dict), "entry is not a JSON object: %r" % (item,)
        assert set(item) == {"path", "size", "sha256"}, (
            "entry must have exactly path/size/sha256: %r" % (item,)
        )
        assert isinstance(item["path"], str), "path is not a string"
        assert isinstance(item["size"], int) and not isinstance(item["size"], bool), (
            "size is not an integer: %r" % (item["size"],)
        )
        digest = item["sha256"]
        assert isinstance(digest, str) and len(digest) == 64, (
            "sha256 must be 64 hex chars: %r" % (digest,)
        )
        assert digest == digest.lower(), "sha256 must be lowercase: %r" % (digest,)
        int(digest, 16)  # raises ValueError if not hex


# ------------------------------------------------------------ requirements


def _req_r1():
    files = {"a.txt": b"alpha\n"}
    proc, raw, payload = _run_manifest(files)
    _expect_ok(proc, payload)
    assert raw is not None, "output file was not created"
    raw.decode("utf-8")
    _check_shape(payload)
    assert payload == _expected(files), "unexpected manifest %r" % (payload,)

    # output placed outside the input directory, nested output name
    work = tempfile.mkdtemp(prefix="manifest-probe-", dir="/tmp")
    root = os.path.join(work, "input")
    os.makedirs(root)
    _build(root, {"one.bin": b"\x00\x01\x02"})
    out_path = os.path.join(work, "sub", "dir.json")
    os.makedirs(os.path.dirname(out_path))
    proc = _run(root, out_path)
    assert proc.returncode == 0, "CLI failed with nested output path: %r" % (
        proc.stderr[-800:],
    )
    with open(out_path, "rb") as fh:
        payload = json.loads(fh.read().decode("utf-8"))
    _check_shape(payload)
    assert payload == _expected({"one.bin": b"\x00\x01\x02"})


def _req_r2():
    files = {
        "top.txt": b"top",
        "pkg/readme.md": b"# readme\n",
        "pkg/inner/readme.md": b"# inner readme\n",
        "pkg/inner/deep/x.bin": b"\xde\xad\xbe\xef",
        "pkg/with space.txt": b"space",
        "pkg/\u00fcber-\u6570\u636e.txt": "unicode \u2713".encode("utf-8"),
        "other/pkg/readme.md": b"other",
    }
    dirs = ("pkg/inner/deep", "empty/nested/leaf", "other")
    proc, raw, payload = _run_manifest(files, dirs=dirs)
    _expect_ok(proc, payload)
    _check_shape(payload)
    expected = _expected(files)
    assert payload == expected, "manifest mismatch:\n got=%r\nwant=%r" % (
        payload,
        expected,
    )
    paths = [item["path"] for item in payload]
    assert all("\\" not in p for p in paths), "path uses backslash separators"
    assert not any(p.startswith("/") for p in paths), "path is absolute"
    # no directory entries leaked into the manifest
    assert not any(p.endswith("/") for p in paths), "directory entry in manifest"
    assert "with space.txt" not in paths, "basename reported instead of relative path"


def _req_r3():
    big = bytes(range(256)) * 400  # 102400 bytes, non-UTF-8 bytes
    files = {
        "empty.dat": b"",
        "bin/raw.bin": b"\xff\xfe\x00\x80not utf8",
        "big/blob.bin": big,
        "z-last.txt": b"last",
        "A-first.txt": b"first",
        "a-lower.txt": b"lower",
        "nested/\u00e9.txt": b"accent",
    }
    proc, raw, payload = _run_manifest(files, dirs=("nested",))
    _expect_ok(proc, payload)
    _check_shape(payload)
    expected = _expected(files)
    assert payload == expected, "content digests/sizes wrong:\n got=%r\nwant=%r" % (
        payload,
        expected,
    )
    paths = [item["path"] for item in payload]
    assert paths == sorted(paths), "entries not sorted by Python string order"
    assert paths == sorted(files), "paths do not match input tree"

    # only empty directories -> []
    proc, raw, payload = _run_manifest({}, dirs=("only/empty", "another"))
    _expect_ok(proc, payload)
    assert payload == [], "empty tree must produce []: %r" % (payload,)

    # single empty file still listed
    proc, raw, payload = _run_manifest({"zero.bin": b""})
    _expect_ok(proc, payload)
    _check_shape(payload)
    assert payload == [{"path": "zero.bin", "size": 0, "sha256": _sha(b"")}], (
        "empty file entry wrong: %r" % (payload,)
    )


def _req_r4():
    work = tempfile.mkdtemp(prefix="manifest-probe-", dir="/tmp")
    root = os.path.join(work, "input")
    os.makedirs(root)
    files = {
        "keep.txt": b"keep me",
        "sub/keep.bin": b"\x00\x01",
        "sub/deeper/zero": b"",
        "lonely/deeper/leaf.txt": b"leaf",
    }
    _build(root, files)
    os.makedirs(os.path.join(root, "lonely", "empty"))
    os.makedirs(os.path.join(root, "totally-empty"))
    before = _snapshot(root)
    out_path = os.path.join(work, "out.json")
    proc = _run(root, out_path)
    assert proc.returncode == 0, "CLI failed: %r" % (proc.stderr[-800:],)
    after = _snapshot(root)
    assert before == after, "input directory tree was modified"

    # second run is stable and does not pollute the tree
    with open(out_path, "rb") as fh:
        first = fh.read()
    proc = _run(root, out_path)
    assert proc.returncode == 0, "second run failed: %r" % (proc.stderr[-800:],)
    with open(out_path, "rb") as fh:
        second = fh.read()
    assert first == second, "manifest output is not stable across runs"
    assert _snapshot(root) == before, "second run modified the input tree"

    # import scan: every module imported by the CLI at runtime is stdlib or local
    src_dir = "/app/src"
    probe_code = (
        "import json, runpy, sys, sysconfig, os\n"
        "stdlib = set(sys.stdlib_module_names) | {'__main__'}\n"
        "local = {n[:-3] for n in os.listdir(%r) if n.endswith('.py')}\n"
        "sys.argv = ['manifest.py', %r, %r]\n"
        "try:\n"
        "    runpy.run_path(%r, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "ours = {m.split('.')[0] for m in sys.modules}\n"
        "bad = sorted(m for m in ours\n"
        "             if m not in stdlib and m not in local\n"
        "             and not m.startswith('_')\n"
        "             and 'site-packages' not in str(getattr(sys.modules.get(m), '__file__', '')))\n"
        "bad = [m for m in bad if getattr(sys.modules.get(m), '__file__', None)\n"
        "       and str(sys.modules[m].__file__).startswith(%r)]\n"
        "print(json.dumps(bad))\n"
    ) % (
        src_dir,
        root,
        os.path.join(work, "scan.json"),
        os.path.join(src_dir, "manifest.py"),
        src_dir,
    )
    scan = subprocess.run(
        ["python", "-c", probe_code],
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=dict(os.environ, PYTHONPATH=src_dir),
    )
    assert scan.returncode == 0, "import scan failed: %r" % (scan.stderr[-800:],)
    offending = json.loads(scan.stdout.decode("utf-8").strip().splitlines()[-1])
    assert offending == [], "non-stdlib imports: %r" % (offending,)
    assert _snapshot(root) == before, "import scan modified the input tree"


_HANDLERS = {"R1": _req_r1, "R2": _req_r2, "R3": _req_r3, "R4": _req_r4}


def check(requirement_id):
    if requirement_id not in _HANDLERS:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    _HANDLERS[requirement_id]()
