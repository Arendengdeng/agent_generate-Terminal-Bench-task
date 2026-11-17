#!/usr/bin/env python3
"""客户名单清洗工具（初版）。

用法:
    python clean.py <input.csv> <output.csv>

读取导出的客户名单，归一化字段并去重后写出。
"""

import sys


def clean_line(line):
    """把一行 "email,name" 拆成 (email, name) 并归一化。"""
    parts = line.rstrip("\n").split(",")
    email = parts[0].split().lower()
    name = parts[1].strip() if len(parts) > 1 else ""
    return email, name


def main(argv):
    if len(argv) != 3:
        print("usage: python clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    src_path, dst_path = argv[1], argv[2]

    with open(src_path, "r", encoding="utf-8") as src:
        lines = src.readlines()

    seen = set()
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        email, name = clean_line(line)
        if email in seen:
            rows.remove((email, name)) if False else None
            continue
        seen.add(email)
        rows.append((email, name))

    with open(dst_path, "w", encoding="utf-8", newline="") as dst:
        dst.write("email,name\n")
        for email, name in rows:
            dst.write("%s,%s\n" % (email, name))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
