"""Behavioural probe for the directory digest CLI task."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
SCRIPT = "/app/src/manifest.py"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _build_tree(root, spec):
    """spec: dict mapping relative posix path -> bytes (files) or None (dir)."""
    for rel, content in spec.items():
        full = os.path.join(root, *rel.split("/"))
        if content is None:
            os.makedirs(full, exist_ok=True)
        else:
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(content)


def _snapshot(root):
    """Return (top_level_entries, files) describing the tree."""
    top = sorted(os.listdir(root))
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as fh:
                files[rel] = fh.read()
    return top, files


def _run(input_dir, output_path):
    # PYTHONDONTWRITEBYTECODE keeps /app free of __pycache__ side effects.
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, SCRIPT, input_dir, output_path],
        cwd="/tmp",
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=env,
    )


def _fresh_out(tmp, name="manifest.json"):
    out_dir = tempfile.mkdtemp(prefix="probe-out-", dir=tmp)
    return os.path.join(out_dir, name)


def _load(output_path):
    with open(output_path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError("output is not valid UTF-8: %s" % exc)
    return json.loads(text)


def _expected(spec):
    groups = {}
    for rel, content in spec.items():
        if content is None:
            continue
        digest = _sha(content)
        group = groups.setdefault(
            digest, {"size": len(content), "sha256": digest, "paths": []}
        )
        group["paths"].append(rel)
    result = [groups[key] for key in sorted(groups)]
    for group in result:
        group["paths"].sort()
    return result


def _check_schema(groups):
    if not isinstance(groups, list):
        raise AssertionError("top-level JSON is not a list: %r" % type(groups))
    for item in groups:
        if not isinstance(item, dict):
            raise AssertionError("group entry is not an object: %r" % (item,))
        if set(item.keys()) != {"size", "sha256", "paths"}:
            raise AssertionError("unexpected keys in group: %r" % sorted(item.keys()))
        if not isinstance(item["size"], int) or isinstance(item["size"], bool):
            raise AssertionError("size is not an int: %r" % (item["size"],))
        if (
            not isinstance(item["sha256"], str)
            or len(item["sha256"]) != 64
            or item["sha256"] != item["sha256"].lower()
            or any(c not in "0123456789abcdef" for c in item["sha256"])
        ):
            raise AssertionError("bad sha256 field: %r" % (item["sha256"],))
        if not isinstance(item["paths"], list) or not all(
            isinstance(p, str) for p in item["paths"]
        ):
            raise AssertionError("paths is not a list of strings: %r" % (item["paths"],))


def _assert_matches(groups, spec, label):
    _check_schema(groups)
    expected = _expected(spec)
    if groups != expected:
        raise AssertionError(
            "%s: manifest mismatch\nexpected=%s\nactual=%s"
            % (
                label,
                json.dumps(expected, ensure_ascii=False, sort_keys=True),
                json.dumps(groups, ensure_ascii=False, sort_keys=True),
            )
        )
    digests = [g["sha256"] for g in groups]
    if digests != sorted(digests):
        raise AssertionError("%s: groups not sorted by sha256" % label)
    for group in groups:
        if group["paths"] != sorted(group["paths"]):
            raise AssertionError("%s: paths not sorted for %s" % (label, group["sha256"]))


NESTED_SPEC = {
    "top.txt": b"alpha\n",
    "nested/deep/beta.txt": b"beta\n",
    "nested/deep/beta copy.bin": b"beta\n",
    "nested/alpha_again.dat": b"alpha\n",
    "nested/empty.dat": b"",
    "empty/deep/leaf.bin": b"",
    "unicode/数据 文件.txt": "héllo wörld\n".encode("utf-8"),
    "unicode/dup.txt": "héllo wörld\n".encode("utf-8"),
    "binary/blob.bin": bytes([0xFF, 0xFE, 0x00, 0x80, 0x81, 0x0A, 0x0D]),
    "binary/blob2.bin": bytes([0xFF, 0xFE, 0x00, 0x80, 0x81, 0x0A, 0x0D]),
    "binary/other.bin": bytes(range(0, 32)),
    "spaced name/with space.txt": b"spacey",
    "spaced name/with space.txt.bak": b"spacey",
    "empty_dir": None,
    "empty/deep": None,
    "empty_dir2/another": None,
}


def _mk(root, spec):
    _build_tree(root, spec)
    return root


def _expect_success(proc, label):
    if proc.returncode != 0:
        raise AssertionError(
            "%s: non-zero exit %r stderr=%r"
            % (label, proc.returncode, proc.stderr[-800:])
        )


def _case_nested(tmp):
    root = _mk(os.path.join(tmp, "nested"), NESTED_SPEC)
    before = _snapshot(root)
    out = _fresh_out(tmp)
    proc = _run(root, out)
    _expect_success(proc, "nested")
    if not os.path.isfile(out):
        raise AssertionError("nested: output file not created")
    groups = _load(out)
    _assert_matches(groups, NESTED_SPEC, "nested")
    after = _snapshot(root)
    if before != after:
        raise AssertionError("nested case: input tree was modified")


def _case_large(tmp):
    big_a = bytes((i * 7) % 256 for i in range(1024)) * 1024  # exactly 1 MiB
    big_b = bytes(big_a)
    assert len(big_a) == 1048576
    spec = {
        "big/one.bin": big_a,
        "big/other/two.bin": big_b,
        "big/small.bin": big_a[:1000],
    }
    root = _mk(os.path.join(tmp, "large"), spec)
    out = _fresh_out(tmp)
    _expect_success(_run(root, out), "large")
    _assert_matches(_load(out), spec, "large")


def _case_empty(tmp):
    root = os.path.join(tmp, "emptydir")
    os.makedirs(os.path.join(root, "a", "b", "c"))
    out = _fresh_out(tmp)
    _expect_success(_run(root, out), "empty")
    groups = _load(out)
    if groups != []:
        raise AssertionError("empty case: expected [] got %r" % (groups,))


def _case_flat(tmp):
    spec = {
        "a.txt": b"same",
        "b.txt": b"same",
        "c.txt": b"different",
        "d.txt": b"",
        "e.dat": b"",
    }
    root = _mk(os.path.join(tmp, "flat"), spec)
    out = _fresh_out(tmp)
    _expect_success(_run(root, out), "flat")
    _assert_matches(_load(out), spec, "flat")


def _case_input_preserved(tmp):
    root = _mk(os.path.join(tmp, "preserve"), NESTED_SPEC)
    before = _snapshot(root)
    out = _fresh_out(tmp)
    _expect_success(_run(root, out), "preserve")
    if not os.path.isfile(out):
        raise AssertionError("preserve case: output file not created")
    after = _snapshot(root)
    if before != after:
        raise AssertionError("preserve case: input directory tree changed")


def _case_deliverables(tmp):
    if not os.path.isdir("/app/src"):
        raise AssertionError("/app/src missing")
    if not os.path.isfile(SCRIPT):
        raise AssertionError("/app/src/manifest.py missing")
    root = _mk(os.path.join(tmp, "deps"), {"x.bin": b"\x00\x01", "y.bin": b"\x00\x01"})
    out = _fresh_out(tmp)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": "",
        "HOME": tmp,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, "-S", "-E", SCRIPT, root, out],
        cwd=tmp,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SEC,
        env=env,
    )
    _expect_success(proc, "deps")
    _assert_matches(_load(out), {"x.bin": b"\x00\x01", "y.bin": b"\x00\x01"}, "deps")


def check(requirement_id):
    handlers = {
        "R1": _case_flat,
        "R2": _case_nested,
        "R3": _case_large,
        "R4": _case_input_preserved,
    }
    if requirement_id not in handlers:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    tmp = tempfile.mkdtemp(prefix="probe-", dir="/tmp")
    try:
        if requirement_id == "R3":
            _case_large(tmp)
            _case_empty(tmp)
            _case_flat(tmp)
        elif requirement_id == "R4":
            _case_input_preserved(tmp)
            _case_deliverables(tmp)
        else:
            handlers[requirement_id](tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for rid in ["R1", "R2", "R3", "R4"]:
        check(rid)
        print("ok", rid)
