#!/bin/sh
# 参考修复：直接生成修复后的 /app/clean.py（使用 csv 模块正确解析与转义）。
set -eu

cat > /app/clean.py <<'PY'
#!/usr/bin/env python
"""客户名单清洗工具。

用法:
    python clean.py <input.csv> <output.csv>

输入: UTF-8 CSV，表头 email,name。
输出: UTF-8 CSV，表头 email,name；email 去首尾空白后小写；name 仅去首尾空白；
      按归一化 email 稳定去重，保留首次记录及其姓名，顺序为首次出现顺序。
"""

import csv
import io
import sys


def clean(src, dst):
    with open(src, "rb") as fh:
        text = fh.read().decode("utf-8")
    reader = csv.reader(io.StringIO(text, newline=""))

    seen = set()
    rows = []
    for index, row in enumerate(reader):
        if index == 0:
            continue
        if not row:
            continue
        email = (row[0] if len(row) > 0 else "").strip().lower()
        name = (row[1] if len(row) > 1 else "").strip()
        if not email or email in seen:
            continue
        seen.add(email)
        rows.append((email, name))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "name"])
    writer.writerows(rows)

    with open(dst, "wb") as fh:
        fh.write(buf.getvalue().encode("utf-8"))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    clean(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY

chmod +x /app/clean.py
