#!/usr/bin/env python3
"""客户名单清洗工具：读取运营导出的 CSV，归一化字段并按邮箱去重后写出。

用法:
    python /app/clean.py <input.csv> <output.csv>
"""

import csv
import sys


def read_rows(path):
    # 读入全部分行文本，再交给 parse_csv 处理
    with open(path, "r", encoding="utf-8") as handle:
        data = handle.read()
    return parse_csv(data)


def parse_csv(data):
    rows = []
    for line in data.split("\n"):
        if not line.strip():
            continue
        parts = [cell.strip() for cell in line.split(",")]
        if parts[0].lower() == "email" and len(parts) > 1 and parts[1].lower() == "name":
            continue
        rows.append(parts)
    return rows


def normalize(rows):
    seen = set()
    out = []
    for parts in rows:
        email = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        out.append((email.strip(), name.strip()))
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
