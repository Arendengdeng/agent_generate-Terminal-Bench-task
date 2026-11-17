"""行为自检：覆盖 Contract 的 R1..R4，只依赖 /app 下的 CLI 与临时夹具。"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

COMMAND_TIMEOUT_SEC = 10
APP_DIR = "/app"
CLI = "/app/clean.py"


def _run(args, timeout=COMMAND_TIMEOUT_SEC):
    return subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True,
        timeout=timeout,
        cwd="/tmp",
    )


def _write_input(tmpdir, text, name="input.csv"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _parse_output(path):
    import csv

    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _clean(input_text, tmpdir, sub="case"):
    base = os.path.join(tmpdir, sub)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    inp = _write_input(base, input_text)
    out = os.path.join(base, "output.csv")
    proc = _run([inp, out])
    assert proc.returncode == 0, (
        "CLI 退出码非 0: %r stderr=%r" % (proc.returncode, proc.stderr[-800:])
    )
    assert os.path.exists(out), "未生成输出文件"
    return inp, out


def _check_basic_case(tmpdir):
    inp, out = _clean(
        'email,name\n'
        '"Alice@Example.COM  ",  Alice  \n'
        'bob@example.com,"Bob, Jr."\n'
        '  alice@example.com ,Alice Two\n'
        'carol@example.com,Carol\n'
        ',NoEmail\n',
        tmpdir,
        "basic",
    )
    rows = _parse_output(out)
    assert rows[0] == ["email", "name"], "输出表头不规范: %r" % (rows[0],)
    assert rows[1:] == [
        ["alice@example.com", "Alice"],
        ["bob@example.com", "Bob, Jr."],
        ["carol@example.com", "Carol"],
    ], "输出内容不符合去重/归一化规范: %r" % (rows[1:],)
    # 输入保持不变（R4 的一部分，顺带检查）
    assert _read_bytes(inp) == (
        'email,name\n'
        '"Alice@Example.COM  ",  Alice  \n'
        'bob@example.com,"Bob, Jr."\n'
        '  alice@example.com ,Alice Two\n'
        'carol@example.com,Carol\n'
        ',NoEmail\n'
    ).encode("utf-8"), "输入文件被修改"


def r1():
    tmpdir = tempfile.mkdtemp(prefix="probe_r1_")
    try:
        inp, out = _clean(
            'email,name\nx@example.com,X\n', tmpdir, "r1"
        )
        rows = _parse_output(out)
        assert rows == [["email", "name"], ["x@example.com", "X"]], (
            "规范 CSV 输出错误: %r" % (rows,)
        )
        # 退出码 0 已由 _clean 断言；再验证一次显式返回码
        out2 = os.path.join(tmpdir, "r1", "output2.csv")
        proc = _run([inp, out2])
        assert proc.returncode == 0, "退出码应为 0, 实际 %r" % (proc.returncode,)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def r2():
    tmpdir = tempfile.mkdtemp(prefix="probe_r2_")
    try:
        _check_basic_case(tmpdir)
        # 带引号内换行的字段与逗号
        text = (
            'email,name\n'
            '"DAN@Example.com","Dan ""The Dan"", Sr."\n'
            'dan@example.com,Duplicate Dan\n'
            ' eve@example.com ,  Eve  \n'
        )
        inp, out = _clean(text, tmpdir, "r2b")
        rows = _parse_output(out)
        assert rows[0] == ["email", "name"], "表头错误: %r" % (rows[0],)
        assert rows[1] == ["dan@example.com", 'Dan "The Dan", Sr.'], (
            "引号/逗号字段解析错误: %r" % (rows[1:],)
        )
        assert rows[2] == ["eve@example.com", "Eve"], "姓名空白处理错误: %r" % (rows[2],)
        assert len(rows) == 3, "未按归一化邮箱稳定去重: %r" % (rows,)
        assert _read_bytes(inp) == text.encode("utf-8"), "输入文件被修改"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def r3():
    tmpdir = tempfile.mkdtemp(prefix="probe_r3_")
    try:
        _, out = _clean("email,name\n", tmpdir, "header_only")
        assert _read_bytes(out).decode("utf-8").strip() == "email,name", (
            "仅表头输入应仅输出表头: %r" % (_read_bytes(out),)
        )
        # 另一套完全不同的数据（不硬编码示例）
        text = (
            'email,name\n'
            'Zoe@Mail.Org,Zoe\n'
            '"mike@mail.org","Mike, M."\n'
            'zoe@mail.org ,Zoe Clone\n'
            'amy@mail.org,Amy\n'
        )
        _, out = _clean(text, tmpdir, "varied")
        rows = _parse_output(out)
        assert rows == [
            ["email", "name"],
            ["zoe@mail.org", "Zoe"],
            ["mike@mail.org", "Mike, M."],
            ["amy@mail.org", "Amy"],
        ], "多样数据输出不符合规范: %r" % (rows,)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def r4():
    tmpdir = tempfile.mkdtemp(prefix="probe_r4_")
    try:
        text = 'email,name\nDup@Example.com,First\n dup@example.com,Second\n'
        inp, out = _clean(text, tmpdir, "r4")
        assert _read_bytes(inp) == text.encode("utf-8"), "输入文件被修改"
        # 输出不得落在输入路径之外的工作区（这里只验证输出存在且输入未变）
        assert os.path.exists(out), "输出缺失"
        # 只交付 clean.py：不得依赖额外的同目录模块
        app_entries = sorted(
            name
            for name in os.listdir(APP_DIR)
            if not name.startswith(".") and name != "__pycache__"
        )
        assert app_entries == ["clean.py"], (
            "/app 下应只有 clean.py，实际: %r" % (app_entries,)
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


_REQUIREMENTS = {"R1": r1, "R2": r2, "R3": r3, "R4": r4}


def check(requirement_id):
    if requirement_id not in _REQUIREMENTS:
        raise ValueError("未知需求 ID: %r" % (requirement_id,))
    _REQUIREMENTS[requirement_id]()
