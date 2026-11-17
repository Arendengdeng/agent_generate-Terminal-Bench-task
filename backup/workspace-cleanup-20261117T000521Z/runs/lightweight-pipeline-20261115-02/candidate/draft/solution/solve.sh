#!/bin/sh
# 参考修复：重写 /app/clean.py，用标准 csv 模块解析与转义，按归一化邮箱稳定去重。
set -e
cat > /app/clean.py <<'PY'
#!/usr/bin/env python3
"""客户名单清洗工具。

用法:
    python clean.py <input.csv> <output.csv>

读取导出的客户名单（表头 email,name），
邮箱去首尾空白并转小写，姓名仅去首尾空白，
按归一化邮箱稳定去重（保留首次出现的姓名），
输出顺序为首次出现顺序，使用 CSV 转义规则。
"""

import csv
import sys


def main(argv):
    if len(argv) != 3:
        print("usage: python clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    src_path, dst_path = argv[1], argv[2]

    with open(src_path, "r", encoding="utf-8", newline="") as src:
        reader = csv.reader(src)
        rows = list(reader)

    records = []
    if rows and rows[0]:
        header = [h.strip().lower() for h in rows[0]]
        start = 1
    else:
        header = ["email", "name"]
        start = 0

    if header[:2] != ["email", "name"]:
        print("error: unexpected header %r" % (rows[0] if rows else None),
              file=sys.stderr)
        return 2

    seen = set()
    out = []
    for row in rows[start:]:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        email = (row[0] if len(row) > 0 else "").strip().lower()
        name = (row[1] if len(row) > 1 else "").strip()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        out.append((email, name))

    with open(dst_path, "w", encoding="utf-8", newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["email", "name"])
        for email, name in out:
            writer.writerow([email, name])

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
chmod +x /app/clean.py
