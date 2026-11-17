"""Behavioral probes for the directory manifest CLI contract."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile

COMMAND_TIMEOUT_SEC = 10
CLI = "/app/src/manifest.py"


def _run_cli(input_dir, output_path):
    proc = subprocess.run(
        ["python", "-B", CLI, input_dir, output_path],
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
    )
    assert proc.returncode == 0, (
        "manifest CLI failed: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
    )
    assert os.path.isfile(output_path), "manifest output file was not created"
    with open(output_path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError("output is not valid UTF-8: %r" % (exc,))
    try:
        return json.loads(text)
    except ValueError as exc:
        raise AssertionError("output is not valid JSON: %r" % (exc,))


def _write(base, rel, data):
    path = os.path.join(base, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _expected(files):
    """files: mapping rel posix path -> bytes. Returns expected manifest."""
    groups = {}
    for rel in sorted(files):
        sha = hashlib.sha256(files[rel]).hexdigest()
        groups.setdefault(sha, []).append(rel)
    entries = []
    for sha in sorted(groups):
        paths = sorted(groups[sha])
        entries.append({"size": len(files[paths[0]]), "sha256": sha, "paths": paths})
    return entries


def _normalize(entries):
    assert isinstance(entries, list), "manifest root must be a JSON array"
    normalized = []
    for entry in entries:
        assert isinstance(entry, dict), "manifest entry must be a JSON object"
        assert set(entry.keys()) == {"size", "sha256", "paths"}, (
            "manifest entry keys must be exactly size/sha256/paths: %r"
            % (sorted(entry.keys()),)
        )
        assert isinstance(entry["size"], int) and not isinstance(entry["size"], bool), (
            "size must be an integer: %r" % (entry["size"],)
        )
        assert isinstance(entry["sha256"], str), "sha256 must be a string"
        assert isinstance(entry["paths"], list), "paths must be a list"
        assert all(isinstance(p, str) for p in entry["paths"]), (
            "paths must contain strings"
        )
        normalized.append(
            {
                "size": entry["size"],
                "sha256": entry["sha256"],
                "paths": list(entry["paths"]),
            }
        )
    return normalized


def _assert_manifest(entries, files):
    normalized = _normalize(entries)
    expected = _expected(files)
    shas = [entry["sha256"] for entry in normalized]
    for sha in shas:
        assert len(sha) == 64 and sha == sha.lower(), (
            "sha256 must be 64 lowercase hex characters: %r" % (sha,)
        )
        int(sha, 16)
    assert shas == sorted(shas), "entries must be sorted by sha256: %r" % (shas,)
    for entry in normalized:
        assert entry["paths"] == sorted(entry["paths"]), (
            "paths must be in ascending order: %r" % (entry["paths"],)
        )
        assert len(entry["paths"]) == len(set(entry["paths"])), (
            "paths must not contain duplicates: %r" % (entry["paths"],)
        )
        for rel in entry["paths"]:
            assert "\\" not in rel, "paths must use POSIX separators: %r" % (rel,)
    assert normalized == expected, (
        "manifest mismatch:\nexpected=%r\nactual=%r" % (expected, normalized)
    )


def _snapshot(root):
    snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in dirnames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            snapshot[rel + "/"] = None
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as handle:
                snapshot[rel] = handle.read()
    return snapshot


def _nested_fixture(root):
    files = {}
    files["top.txt"] = b"top level payload\n"
    files["notes/readme.txt"] = b"top level payload\n"
    files["notes/deep/readme.txt"] = b"top level payload\n"
    files["存档 目录/归档 1.bin"] = bytes([0x00, 0xFF, 0x80, 0x41, 0x00, 0x42])
    files["存档 目录/deep/归档 1 copy.bin"] = bytes([0x00, 0xFF, 0x80, 0x41, 0x00, 0x42])
    files["deep/a/b/c/d/e/f/g/leaf.dat"] = b"leaf contents"
    files["empty/file0"] = b""
    files["empty/zero copy"] = b""
    files["with space/same name.txt"] = b"same-name group"
    files["other/same name.txt"] = b"same-name group"
    for rel, data in files.items():
        _write(root, rel, data)
    os.makedirs(os.path.join(root, "empty-dir"), exist_ok=True)
    os.makedirs(os.path.join(root, "deep", "empty-sub"), exist_ok=True)
    return files


def _check_r1():
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "in")
        files = {
            "a.txt": b"hello world\n",
            "sub/b.bin": bytes(range(0, 40)) + bytes([0, 255, 254]),
            "sub/deeper/c.txt": b"hello world\n",
        }
        for rel, data in files.items():
            _write(src, rel, data)
        out = os.path.join(tmp, "out.json")
        entries = _run_cli(src, out)
        _assert_manifest(entries, files)

        first = open(out, "rb").read()
        entries = _run_cli(src, out)
        _assert_manifest(entries, files)
        assert open(out, "rb").read() == first, (
            "repeated runs on unchanged input must produce identical output"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_r2():
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "tree")
        files = _nested_fixture(src)
        out = os.path.join(tmp, "manifest.json")
        entries = _run_cli(src, out)
        _assert_manifest(entries, files)
        seen = set()
        for entry in entries:
            seen.update(entry["paths"])
        assert seen == set(files), "all regular files must be reported exactly once"
        assert "notes/deep/readme.txt" in seen, "nested files must use POSIX relative paths"
        assert "deep/a/b/c/d/e/f/g/leaf.dat" in seen, "deep nesting must be traversed"
        assert "存档 目录/归档 1.bin" in seen, "Unicode/space names must be preserved"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_r3():
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "binary")
        payload = bytes(range(256)) * 3
        invalid_bytes = bytes([0xC3, 0x28, 0xA0, 0xA1, 0xFF, 0x00])
        files = {
            "raw/blob.dat": payload,
            "raw/blob copy.dat": payload,
            "raw/empty.bin": b"",
            "nested/empty copy.bin": b"",
            "nested/invalid-utf8.bin": invalid_bytes,
            "prefix-aa": b"aa",
            "prefix-ab": b"ab",
            "大小/零 字节": b"",
        }
        for rel, data in files.items():
            _write(src, rel, data)
        out = os.path.join(tmp, "m.json")
        entries = _run_cli(src, out)
        _assert_manifest(entries, files)
        by_sha = {entry["sha256"]: entry for entry in entries}
        empty = by_sha.get(hashlib.sha256(b"").hexdigest())
        assert empty is not None, "empty files must form a group"
        assert empty["size"] == 0, "empty file group size must be 0"
        assert empty["paths"] == [
            "nested/empty copy.bin",
            "raw/empty.bin",
            "大小/零 字节",
        ], "empty group paths wrong: %r" % (empty["paths"],)
        blob = by_sha.get(hashlib.sha256(payload).hexdigest())
        assert blob is not None, "binary payload group missing"
        assert blob["size"] == len(payload), (
            "size must be measured in bytes: %r != %r" % (blob["size"], len(payload))
        )
        invalid = by_sha.get(hashlib.sha256(invalid_bytes).hexdigest())
        assert invalid is not None, "non UTF-8 file must be digested by raw bytes"
        assert invalid["size"] == 6, "non UTF-8 file size must be byte length"
        shas = [entry["sha256"] for entry in entries]
        assert shas == sorted(set(shas)), "each sha256 must appear once, sorted ascending"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_r4():
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "keep")
        files = _nested_fixture(src)
        os.makedirs(os.path.join(src, "空 目录", "inner"), exist_ok=True)
        before = _snapshot(src)
        out = os.path.join(tmp, "outside.json")
        entries = _run_cli(src, out)
        _assert_manifest(entries, files)
        after = _snapshot(src)
        assert before == after, "input directory tree must not be modified"
        assert not os.path.exists(os.path.join(src, "outside.json")), (
            "output must be written to the requested location outside the input dir"
        )
        names = set(os.listdir(src))
        assert names == {
            "top.txt",
            "notes",
            "存档 目录",
            "deep",
            "empty",
            "with space",
            "other",
            "empty-dir",
            "空 目录",
        }, "no extra entries may appear inside the input dir: %r" % (sorted(names),)

        only_dirs = os.path.join(tmp, "only-dirs")
        os.makedirs(os.path.join(only_dirs, "x", "y"), exist_ok=True)
        empty_out = os.path.join(tmp, "empty.json")
        entries = _run_cli(only_dirs, empty_out)
        assert _normalize(entries) == [], "tree without regular files must yield []"

        for name in ("manifest.py", "walker.py", "digest.py", "groups.py"):
            assert os.path.isfile(os.path.join("/app/src", name)), (
                "/app/src/%s must exist" % (name,)
            )
        isolated_out = os.path.join(tmp, "isolated.json")
        script = "/app/src/manifest.py"
        launcher = (
            "import runpy, sys\n"
            "sys.argv = [sys.argv[1], sys.argv[2], sys.argv[3]]\n"
            "runpy.run_path(sys.argv[0], run_name='__main__')\n"
        )
        proc = subprocess.run(
            ["python", "-B", "-c", launcher, script, src, isolated_out],
            cwd=tmp,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SEC,
        )
        assert proc.returncode == 0, (
            "CLI must run from outside /app using only the stdlib: rc=%r stderr=%r"
            % (proc.returncode, proc.stderr)
        )
        assert os.path.isfile(isolated_out), (
            "CLI run from another working directory must produce output"
        )
        with open(isolated_out, "r", encoding="utf-8") as handle:
            _assert_manifest(json.load(handle), files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_CHECKS = {
    "R1": _check_r1,
    "R2": _check_r2,
    "R3": _check_r3,
    "R4": _check_r4,
}


def check(requirement_id):
    handler = _CHECKS.get(requirement_id)
    if handler is None:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    handler()
