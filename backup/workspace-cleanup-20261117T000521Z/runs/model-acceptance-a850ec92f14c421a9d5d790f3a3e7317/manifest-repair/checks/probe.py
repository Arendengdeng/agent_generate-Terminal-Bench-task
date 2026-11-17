"""行为探针：逐条校验 Contract 的需求。

每个 check(requirement_id) 在独立临时目录中构造输入、运行 CLI，
并断言真实输出。Unknown ID 抛 ValueError；任务行为不符抛 AssertionError。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP = "/app"
MANIFEST = os.path.join(APP, "src", "manifest.py")
PY = sys.executable or "python3"

R1 = "R1"
R2 = "R2"
R3 = "R3"
R4 = "R4"
KNOWN = {R1, R2, R3, R4}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def run_cli(args, timeout=COMMAND_TIMEOUT_SEC):
    return subprocess.run(
        [PY, MANIFEST] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/tmp",
    )


def make_tree(base, files, dirs=()):
    """files: list of (rel_posix_path, bytes)。"""
    root = os.path.join(base, "input dir")
    os.makedirs(root)
    for d in dirs:
        os.makedirs(os.path.join(root, *d.split("/")), exist_ok=True)
    for rel, data in files:
        target = os.path.join(root, *rel.split("/"))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
    return root


def expected_records(files):
    records = [
        {
            "path": rel,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for rel, data in files
    ]
    records.sort(key=lambda r: r["path"])
    return records


def load_output(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def snapshot(root):
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as handle:
                data = handle.read()
            entries.append((rel, hashlib.sha256(data).hexdigest(), len(data)))
    return sorted(entries)


class Sandbox(object):
    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="manifest-probe-", dir="/tmp")
        self.tree = os.path.join(self.base, "tree")
        os.makedirs(self.tree)
        self.out = os.path.join(self.base, "manifest.json")

    def make(self, files, dirs=()):
        return make_tree(self.tree, files, dirs)

    def cleanup(self):
        shutil.rmtree(self.base, ignore_errors=True)


def check_manifest_equal(got, want):
    assert isinstance(got, list), "输出不是 JSON 数组: %r" % (got,)
    for item in got:
        assert isinstance(item, dict), "数组元素不是对象: %r" % (item,)
        assert set(item.keys()) == {"path", "size", "sha256"}, "键集合不正确: %r" % (sorted(item.keys()),)
        assert isinstance(item["path"], str), "path 不是字符串"
        assert isinstance(item["size"], int) and not isinstance(item["size"], bool), "size 不是整数"
        assert isinstance(item["sha256"], str), "sha256 不是字符串"
        assert len(item["sha256"]) == 64 and all(c in "0123456789abcdef" for c in item["sha256"]), (
            "sha256 格式不正确: %r" % (item["sha256"],)
        )
    assert got == want, "清单不匹配\n expected=%s\n actual=%s" % (
        json.dumps(want, ensure_ascii=False),
        json.dumps(got, ensure_ascii=False),
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def nested_fixture():
    files = [
        ("README.md", b"root readme\n"),
        ("docs/README.md", b"docs readme, different\n"),
        ("docs/2023/README.md", b"nested readme\n"),
        ("docs/old project/manual v2.txt", b"manual\n"),
        ("docs/旧项目/说明.txt", "中文内容测试\n".encode("utf-8")),
        ("data/Ünïcodé fïlé.bin", b"\x00\x01\x02"),
    ]
    dirs = ["empty dir/level1/level2", "docs/2023", "docs/旧项目"]
    return files, dirs


def mixed_fixture():
    big = bytes((i * 7 + 3) % 256 for i in range(1 << 20))
    files = [
        ("empty.bin", b""),
        ("bin/raw.dat", b"\x00\xff\xfe\x80 \xe9\xff not utf8\n"),
        ("big/last.bin", big),
        ("upper/B.txt", b"B\n"),
        ("upper/a.txt", b"a\n"),
        ("upper/space name.txt", b"spaces\n"),
    ]
    dirs = ["only/empty/dirs"]
    return files, dirs


def sorted_paths(files):
    return sorted(rel for rel, _ in files)


# --------------------------------------------------------------------------
# requirement checks
# --------------------------------------------------------------------------
def _check_r1():
    box = Sandbox()
    try:
        files, dirs = nested_fixture()
        root = box.make(files, dirs)
        proc = run_cli([root, box.out])
        assert proc.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
        assert os.path.isfile(box.out), "未生成输出文件: %r" % (box.out,)
        with open(box.out, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
        assert isinstance(data, list), "输出不是 JSON 数组"
    finally:
        box.cleanup()


def _check_r2():
    box = Sandbox()
    try:
        files, dirs = nested_fixture()
        root = box.make(files, dirs)
        proc = run_cli([root, box.out])
        assert proc.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
        got = load_output(box.out)
        assert isinstance(got, list), "输出不是 JSON 数组"
        paths = []
        for item in got:
            assert isinstance(item, dict) and isinstance(item.get("path"), str), "缺少 path 字段: %r" % (item,)
            paths.append(item["path"])
        want_paths = sorted_paths(files)
        assert paths == want_paths, "相对路径集合或顺序不正确\n expected=%r\n actual=%r" % (
            want_paths, paths,
        )
        for item in got:
            assert "size" in item and "sha256" in item, "缺少 size/sha256 字段: %r" % (item,)

        box2 = Sandbox()
        try:
            files2 = [("a/b c.txt", b"1"), ("a/b.txt", b"2"), ("a/b-c.txt", b"3"),
                      ("dir with space/deep/x y/z.txt", b"4")]
            root2 = box2.make(files2)
            proc2 = run_cli([root2, box2.out])
            assert proc2.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc2.returncode, proc2.stderr)
            got2 = load_output(box2.out)
            check_manifest_equal(sorted(got2, key=lambda r: r["path"]), expected_records(files2))
        finally:
            box2.cleanup()
    finally:
        box.cleanup()


def _check_r3():
    box = Sandbox()
    try:
        files, dirs = mixed_fixture()
        root = box.make(files, dirs)
        proc = run_cli([root, box.out])
        assert proc.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
        got = load_output(box.out)
        want = expected_records(files)
        check_manifest_equal(got, want)
        by_path = {item["path"]: item for item in got}
        empty = by_path["empty.bin"]
        assert empty["size"] == 0, "空文件 size 不正确: %r" % (empty,)
        assert empty["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", (
            "空文件摘要不正确: %r" % (empty,)
        )
        assert by_path["big/last.bin"]["size"] == 1 << 20, "1 MiB 文件 size 不正确"
        # 稳定排序：两次运行结果一致。
        out2 = os.path.join(box.base, "second.json")
        proc2 = run_cli([root, out2])
        assert proc2.returncode == 0, "第二次运行失败: rc=%r stderr=%r" % (proc2.returncode, proc2.stderr)
        assert load_output(out2) == got, "两次运行的清单不一致"
    finally:
        box.cleanup()

    # 空目录（无任何文件）应输出 []。
    box = Sandbox()
    try:
        root = box.make([], ["a/b/c", "d"])
        proc = run_cli([root, box.out])
        assert proc.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
        got = load_output(box.out)
        assert got == [], "空目录应输出 []，实际: %r" % (got,)
    finally:
        box.cleanup()


def _check_r4():
    box = Sandbox()
    try:
        files, dirs = nested_fixture()
        root = box.make(files, dirs)
        before = snapshot(root)
        proc = run_cli([root, box.out])
        assert proc.returncode == 0, "CLI 未正常退出: rc=%r stderr=%r" % (proc.returncode, proc.stderr)
        after = snapshot(root)
        assert after == before, "输入目录树被修改:\n before=%r\n after=%r" % (before, after)

        # 所有交付模块位于 /app/src，且只依赖标准库（以 -I 隔离模式排除 PYTHONPATH 干扰）。
        assert os.path.isfile(MANIFEST), "缺少 /app/src/manifest.py"
        out_iso = os.path.join(box.base, "iso.json")
        proc2 = subprocess.run(
            [PY, "-I", "-B", MANIFEST, root, out_iso],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            cwd="/tmp",
        )
        assert proc2.returncode == 0, "隔离模式下运行失败（可能依赖环境变量或非标准库）: rc=%r stderr=%r" % (
            proc2.returncode, proc2.stderr,
        )
        got = load_output(out_iso)
        assert isinstance(got, list), "隔离模式输出不是 JSON 数组"
        assert sorted(item.get("path") for item in got) == sorted_paths(files), (
            "隔离模式下的路径集合不正确"
        )
        assert snapshot(root) == before, "-I 模式下输入目录树被修改"
    finally:
        box.cleanup()


CHECKS = {
    R1: _check_r1,
    R2: _check_r2,
    R3: _check_r3,
    R4: _check_r4,
}


def check(requirement_id):
    if requirement_id not in KNOWN:
        raise ValueError("unknown requirement id: %r" % (requirement_id,))
    CHECKS[requirement_id]()


if __name__ == "__main__":
    failed = 0
    for rid in [R1, R2, R3, R4]:
        try:
            check(rid)
        except AssertionError as exc:
            failed += 1
            print("%s FAIL: %s" % (rid, exc))
        else:
            print("%s PASS" % rid)
    sys.exit(1 if failed else 0)
