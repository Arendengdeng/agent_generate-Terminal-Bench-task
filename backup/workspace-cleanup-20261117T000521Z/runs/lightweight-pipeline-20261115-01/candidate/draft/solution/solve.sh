#!/bin/sh
set -eu
cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""客户名单清洗工具：读取运营导出的 CSV，归一化字段并按邮箱去重后写出。

用法:
    python /app/clean.py <input.csv> <output.csv>

规范:
  * 输入/输出均为 UTF-8 CSV，表头恰为 email,name，遵循标准 CSV 引号规则。
  * email 去掉首尾空白后转小写；name 仅去掉首尾空白。
  * 按归一化 email 去重，保留第一次出现的姓名，输出保持首次出现顺序。
"""

import csv
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if rows:
        head = [cell.strip().lower() for cell in rows[0]]
        if head == ["email", "name"]:
            rows = rows[1:]
    return rows


def normalize(rows):
    seen = set()
    out = []
    for parts in rows:
        if not parts:
            continue
        email_raw = parts[0] if len(parts) > 0 else ""
        name_raw = parts[1] if len(parts) > 1 else ""
        email = email_raw.strip().lower()
        name = name_raw.strip()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        out.append((email, name))
    return out


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法: python clean.py <input.csv> <output.csv>\n")
        return 2
    rows = read_rows(argv[1])
    cleaned = normalize(rows)
    write_rows(argv[2], cleaned)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
