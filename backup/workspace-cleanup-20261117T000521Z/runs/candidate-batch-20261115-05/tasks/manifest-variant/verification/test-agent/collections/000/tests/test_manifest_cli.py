"""Independent behavioural tests for the directory manifest CLI at /app/src/manifest.py.

Tests build their own fixture trees under /tmp, run the CLI as a subprocess, and
compare the emitted JSON manifest against expectations computed directly from
the fixture bytes with hashlib.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

SCRIPT = "/app/src/manifest.py"
SRC_DIR = "/app/src"
TIMEOUT = 10


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def run_cli(input_dir, output_path, cwd="/"):
    """Run the task CLI and return the completed process (captured output)."""
    cmd = [sys.executable, SCRIPT, str(input_dir), str(output_path)]
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("manifest CLI timed out after %s seconds: %r" % (TIMEOUT, cmd))


def sha_of(data):
    return hashlib.sha256(data).hexdigest()


def expected_manifest(root):
    """Compute the expected manifest (per contract) directly from the fixture tree."""
    root = str(root)
    groups = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            absolute = os.path.join(dirpath, name)
            if not os.path.isfile(absolute) or os.path.islink(absolute):
                continue
            relative = os.path.relpath(absolute, root).replace(os.sep, "/")
            with open(absolute, "rb") as handle:
                data = handle.read()
            sha = sha_of(data)
            groups.setdefault(sha, {"size": len(data), "paths": []})
            groups[sha]["paths"].append(relative)
    entries = []
    for sha in sorted(groups):
        entries.append({
            "size": groups[sha]["size"],
            "sha256": sha,
            "paths": sorted(groups[sha]["paths"]),
        })
    return entries


def snapshot_tree(root):
    """Return an ordered snapshot of the input tree: dirs/files and file bytes."""
    root = str(root)
    snapshot = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        snapshot.append(("dir", rel_dir))
        for name in filenames:
            absolute = os.path.join(dirpath, name)
            relative = os.path.relpath(absolute, root).replace(os.sep, "/")
            with open(absolute, "rb") as handle:
                snapshot.append(("file", relative, handle.read()))
    return snapshot


def write_file(root, rel_path, data):
    absolute = os.path.join(str(root), *rel_path.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "wb") as handle:
        handle.write(data)
    return absolute


def load_manifest(output_path):
    """Load and validate the basic JSON shape of the produced manifest."""
    output_path = str(output_path)
    assert os.path.isfile(output_path), "CLI did not create the output file"
    with open(output_path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:  # expected failure -> AssertionError
        raise AssertionError("output is not valid UTF-8: %r" % (exc,))
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError("output is not valid JSON: %r" % (exc,))
    assert isinstance(manifest, list), "manifest is not a JSON array: %r" % (manifest,)
    return manifest


def check_entry_shape(entry):
    assert isinstance(entry, dict), "entry is not a JSON object: %r" % (entry,)
    assert set(entry.keys()) == {"size", "sha256", "paths"}, (
        "entry keys must be exactly size/sha256/paths, got %r" % (sorted(entry.keys()),)
    )
    assert isinstance(entry["size"], int) and not isinstance(entry["size"], bool), (
        "size is not an integer: %r" % (entry["size"],)
    )
    assert isinstance(entry["sha256"], str), "sha256 is not a string: %r" % (entry["sha256"],)
    assert isinstance(entry["paths"], list), "paths is not a list: %r" % (entry["paths"],)
    assert all(isinstance(path, str) for path in entry["paths"]), (
        "paths contains non-strings: %r" % (entry["paths"],)
    )


def run_and_check(input_dir, tmp_path, cwd="/", expect=None):
    """Run CLI on input_dir, validate output, return the manifest."""
    output_path = os.path.join(str(tmp_path), "manifest.json")
    proc = run_cli(input_dir, output_path, cwd=cwd)
    assert proc.returncode == 0, (
        "CLI exited with %r; stderr=%r" % (proc.returncode, proc.stderr)
    )
    manifest = load_manifest(output_path)
    for entry in manifest:
        check_entry_shape(entry)
    if expect is None:
        expect = expected_manifest(input_dir)
    # full structural comparison: grouping, sizes, digests, ordering, keys
    assert manifest == expect, (
        "manifest mismatch\nactual:   %s\nexpected: %s" % (manifest, expect)
    )
    return manifest


# --------------------------------------------------------------------------- #
# R1: CLI contract
# --------------------------------------------------------------------------- #
def test_r1_cli_creates_output_and_exits_zero(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    write_file(input_dir, "a.txt", b"alpha\n")
    output_path = tmp_path / "out.json"

    proc = run_cli(input_dir, output_path)
    assert proc.returncode == 0, "CLI must exit 0 on success; stderr=%r" % (proc.stderr,)
    assert os.path.isfile(str(output_path)), "CLI did not write the requested JSON file"
    manifest = load_manifest(output_path)
    assert manifest == expected_manifest(input_dir)


def test_r1_cli_works_from_unrelated_working_directory(tmp_path):
    input_dir = tmp_path / "input"
    write_file(input_dir, "sub/x.bin", bytes(range(256)))
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    output_path = tmp_path / "out.json"

    run_and_check(input_dir, tmp_path, cwd=str(work_dir))
    # nothing should have been written inside the working directory
    assert os.listdir(str(work_dir)) == [], (
        "CLI wrote files into its working directory: %r" % (os.listdir(str(work_dir)),)
    )


def test_r1_sample_directory(tmp_path):
    sample = "/app/data/sample"
    if not os.path.isdir(sample):
        pytest.fail("/app/data/sample sample directory is missing")
    run_and_check(sample, tmp_path)


# --------------------------------------------------------------------------- #
# R2: recursion, full path set, grouping
# --------------------------------------------------------------------------- #
def test_r2_nested_same_name_files_all_reported(tmp_path):
    input_dir = tmp_path / "input"
    content = b"same content for every readme\n"
    names = [
        "readme.txt",
        "deep/readme.txt",
        "deep/nested/readme.txt",
        "a/b/c/d/e/f/g/readme.txt",
        "notes/readme.txt",
        "x  y/readme.txt",
    ]
    for name in names:
        write_file(input_dir, name, content)

    manifest = run_and_check(input_dir, tmp_path)
    assert len(manifest) == 1, "identical contents must form one group: %r" % (manifest,)
    assert manifest[0]["paths"] == sorted(names)
    assert manifest[0]["size"] == len(content)


def test_r2_depth_and_unique_files(tmp_path):
    input_dir = tmp_path / "input"
    pairs = []
    for depth in range(1, 9):
        parts = ["d%d" % level for level in range(depth)]
        rel = "/".join(parts + ["f%d.bin" % depth])
        data = ("payload-%d" % depth).encode("ascii")
        write_file(input_dir, rel, data)
        pairs.append((rel, data))

    manifest = run_and_check(input_dir, tmp_path)
    assert len(manifest) == len(pairs)
    seen = set()
    for entry in manifest:
        assert len(entry["paths"]) == 1
        seen.add(entry["paths"][0])
    assert seen == {rel for rel, _ in pairs}


def test_r2_spaces_and_unicode_names(tmp_path):
    input_dir = tmp_path / "input"
    shared = "共享内容 shared\n".encode("utf-8")
    unicode_a = "目录/名字 带空格.txt"
    unicode_b = "另一个 目录/文件 名 二.txt"
    nested_same = "目录/nested/名字 带空格.txt"
    plain = "top level file.txt"
    for name in (unicode_a, unicode_b, nested_same, plain):
        write_file(input_dir, name, shared)

    manifest = run_and_check(input_dir, tmp_path)
    assert len(manifest) == 1, "all four files share content: %r" % (manifest,)
    assert manifest[0]["paths"] == sorted([unicode_a, unicode_b, nested_same, plain])


def test_r2_unicode_sorting_uses_python_string_order(tmp_path):
    input_dir = tmp_path / "input"
    shared = b"unicode order fixture\n"
    names = [
        "z.txt",
        "ä.txt",
        "中.txt",
        "Ω.txt",
        "a b.txt",
        "a.txt",
        "A.txt",
        "sub/ä.txt",
        "sub/z.txt",
        "sub/sub2/ß.txt",
    ]
    for name in names:
        write_file(input_dir, name, shared)

    manifest = run_and_check(input_dir, tmp_path)
    assert len(manifest) == 1
    assert manifest[0]["paths"] == sorted(names)


def test_r2_multiple_groups_keep_all_paths(tmp_path):
    input_dir = tmp_path / "input"
    layout = {
        "one.txt": b"group one\n",
        "sub/one.txt": b"group one\n",
        "sub/deeper/one copy.txt": b"group one\n",
        "two.bin": b"\x00\x01\x02group two\n",
        "sub/two.bin": b"\x00\x01\x02group two\n",
        "three 三.txt": "第三组\n".encode("utf-8"),
        "solo/unique.txt": b"utterly unique payload\n",
    }
    for rel, data in layout.items():
        write_file(input_dir, rel, data)

    manifest = run_and_check(input_dir, tmp_path)
    by_sha = {entry["sha256"]: entry for entry in manifest}
    assert len(by_sha) == 4
    assert by_sha[sha_of(b"group one\n")]["paths"] == sorted(
        ["one.txt", "sub/deeper/one copy.txt", "sub/one.txt"]
    )
    assert by_sha[sha_of(b"\x00\x01\x02group two\n")]["paths"] == sorted(
        ["sub/two.bin", "two.bin"]
    )
    assert by_sha[sha_of("第三组\n".encode("utf-8"))]["paths"] == ["three 三.txt"]
    assert by_sha[sha_of(b"utterly unique payload\n")]["paths"] == ["solo/unique.txt"]


# --------------------------------------------------------------------------- #
# R3: binary content, sizes, digests, ordering, empty inputs
# --------------------------------------------------------------------------- #
def test_r3_empty_directories_only_yield_empty_array(tmp_path):
    input_dir = tmp_path / "input"
    os.makedirs(str(input_dir / "a" / "b" / "c"))
    os.makedirs(str(input_dir / "solo"))
    os.makedirs(str(input_dir / "名字 目录" / "空"))

    output_path = tmp_path / "out.json"
    proc = run_cli(input_dir, output_path)
    assert proc.returncode == 0, "CLI must exit 0; stderr=%r" % (proc.stderr,)
    assert os.path.isfile(str(output_path))
    manifest = load_manifest(output_path)
    assert manifest == [], "tree without files must yield [], got %r" % (manifest,)


def test_r3_completely_empty_input_dir(tmp_path):
    input_dir = tmp_path / "emptyroot"
    input_dir.mkdir()
    manifest = run_and_check(input_dir, tmp_path)
    assert manifest == []


def test_r3_empty_files_grouped_together(tmp_path):
    input_dir = tmp_path / "input"
    for name in ("blank.bin", "sub/blank.bin", "sub/deeper/also empty", "空格 空.txt"):
        write_file(input_dir, name, b"")
    write_file(input_dir, "nonempty.txt", b"x")

    manifest = run_and_check(input_dir, tmp_path)
    empties = [entry for entry in manifest if entry["size"] == 0]
    assert len(empties) == 1, "empty files must be one group: %r" % (manifest,)
    empty_entry = empties[0]
    assert empty_entry["sha256"] == sha_of(b"")
    assert empty_entry["sha256"] == hashlib.sha256(b"").hexdigest()
    assert empty_entry["paths"] == sorted(
        ["blank.bin", "sub/blank.bin", "sub/deeper/also empty", "空格 空.txt"]
    )


def test_r3_binary_and_non_utf8_content(tmp_path):
    input_dir = tmp_path / "input"
    binary = bytes(range(256)) * 3 + b"\xff\xfe\x80\x81"
    invalid_utf8 = b"\xc3\x28\xa0\xa1\xe2\x28\xa1"
    write_file(input_dir, "binary.dat", binary)
    write_file(input_dir, "sub/binary copy.dat", binary)
    write_file(input_dir, "bad utf8.txt", invalid_utf8)
    write_file(input_dir, "nul\x00".join(["name", "with-nul"]) if False else "plain.txt", b"plain\n")

    manifest = run_and_check(input_dir, tmp_path)
    by_sha = {entry["sha256"]: entry for entry in manifest}
    binary_sha = sha_of(binary)
    invalid_sha = sha_of(invalid_utf8)
    assert binary_sha in by_sha, "binary content digest missing"
    assert invalid_sha in by_sha, "non-UTF-8 content digest missing"
    assert by_sha[binary_sha]["size"] == len(binary)
    assert by_sha[binary_sha]["paths"] == sorted(["binary.dat", "sub/binary copy.dat"])
    assert by_sha[invalid_sha]["size"] == len(invalid_utf8)
    assert by_sha[invalid_sha]["paths"] == ["bad utf8.txt"]


def test_r3_size_is_bytes_not_characters(tmp_path):
    input_dir = tmp_path / "input"
    text = "汉字与 emoji 😀 mixed\n"
    data = text.encode("utf-8")
    assert len(data) != len(text)
    write_file(input_dir, "multi.txt", data)
    write_file(input_dir, "repeat/multi.txt", data)

    manifest = run_and_check(input_dir, tmp_path)
    assert len(manifest) == 1
    assert manifest[0]["size"] == len(data)
    assert manifest[0]["sha256"] == sha_of(data)


def test_r3_sha256_is_lowercase_hex(tmp_path):
    input_dir = tmp_path / "input"
    write_file(input_dir, "a.txt", b"abc")
    write_file(input_dir, "b.txt", b"abd")
    write_file(input_dir, "sub/c.bin", b"\xff\x00\xfe")

    manifest = run_and_check(input_dir, tmp_path)
    for entry in manifest:
        sha = entry["sha256"]
        assert len(sha) == 64, "sha256 must be 64 chars: %r" % (sha,)
        assert all(ch in "0123456789abcdef" for ch in sha), (
            "sha256 must be lowercase hex: %r" % (sha,)
        )
        assert sha == sha.lower()
    assert sha_of(b"abc") in {entry["sha256"] for entry in manifest}


def test_r3_entries_sorted_by_sha256_and_paths_sorted(tmp_path):
    input_dir = tmp_path / "input"
    # many small files, several groups, so ordering is exercised broadly
    names = []
    for index in range(20):
        rel = "dir%02d/file %02d.txt" % (index % 5, index)
        write_file(input_dir, rel, ("content-%d" % (index % 7)).encode("ascii"))
        names.append(rel)
    # duplicate group with paths that are not in walk order
    for rel in ("zzz dup", "aaa dup", "mmm/dup"):
        write_file(input_dir, rel, b"dup payload")

    manifest = run_and_check(input_dir, tmp_path)
    shas = [entry["sha256"] for entry in manifest]
    assert shas == sorted(shas), "entries must be sorted by sha256"
    assert len(shas) == len(set(shas))
    for entry in manifest:
        assert entry["paths"] == sorted(entry["paths"]), (
            "paths must be sorted: %r" % (entry["paths"],)
        )
        for path in entry["paths"]:
            assert not path.startswith("/"), "paths must be relative: %r" % (path,)
            assert "\\" not in path, "paths must use POSIX separators: %r" % (path,)


def test_r3_boundary_sha_ordering_matches_expected(tmp_path):
    input_dir = tmp_path / "input"
    payloads = [b"", b"\x00", b"\xff", b"a", b"\x00\x00", b"abc", b"\xff" * 100]
    for index, data in enumerate(payloads):
        write_file(input_dir, "f%d" % index, data)

    manifest = run_and_check(input_dir, tmp_path)
    expected_shas = sorted(sha_of(data) for data in payloads)
    assert [entry["sha256"] for entry in manifest] == expected_shas


# --------------------------------------------------------------------------- #
# R4: input preservation and delivered layout
# --------------------------------------------------------------------------- #
def test_r4_input_tree_is_not_modified(tmp_path):
    input_dir = tmp_path / "input"
    write_file(input_dir, "keep.txt", b"keep me\n")
    write_file(input_dir, "deep/nested/keep.txt", b"keep me\n")
    write_file(input_dir, "deep/nested/blank.bin", b"")
    write_file(input_dir, "名字 带空格.txt", bytes(range(250)))
    os.makedirs(str(input_dir / "empty_dir" / "nested_empty"))
    before = snapshot_tree(input_dir)

    run_and_check(input_dir, tmp_path)

    after = snapshot_tree(input_dir)
    assert after == before, "CLI modified the input tree"


def test_r4_does_not_write_into_input_dir(tmp_path):
    input_dir = tmp_path / "input"
    write_file(input_dir, "a.txt", b"aaa")
    write_file(input_dir, "sub/b.bin", b"\x00\x01")
    os.makedirs(str(input_dir / "empty"))
    before = set()
    for dirpath, dirnames, filenames in os.walk(str(input_dir)):
        for name in dirnames + filenames:
            before.add(os.path.relpath(os.path.join(dirpath, name), str(input_dir)))

    run_and_check(input_dir, tmp_path)

    after = set()
    for dirpath, dirnames, filenames in os.walk(str(input_dir)):
        for name in dirnames + filenames:
            after.add(os.path.relpath(os.path.join(dirpath, name), str(input_dir)))
    assert after == before, "extra entries appeared inside input dir: %r" % (after - before,)


def test_r4_delivered_modules_live_in_app_src():
    assert os.path.isdir(SRC_DIR), "/app/src must exist"
    assert os.path.isfile(SCRIPT), "/app/src/manifest.py must exist"
    # the repaired program must be completable with stdlib only: run with a
    # subprocess whose environment has no third-party site-packages available.
    with tempfile.TemporaryDirectory() as tmp:
        input_dir = os.path.join(tmp, "input")
        os.makedirs(input_dir)
        with open(os.path.join(input_dir, "f.txt"), "wb") as handle:
            handle.write(b"stdlib only\n")
        output_path = os.path.join(tmp, "out.json")
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        try:
            proc = subprocess.run(
                [sys.executable, "-S", SCRIPT, input_dir, output_path],
                cwd="/",
                capture_output=True,
                timeout=TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("manifest CLI timed out under minimal environment")
        assert proc.returncode == 0, (
            "CLI must run with the standard library only; stderr=%r" % (proc.stderr,)
        )
        manifest = load_manifest(output_path)
        assert manifest == expected_manifest(input_dir)
