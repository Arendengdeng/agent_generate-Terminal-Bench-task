#!/usr/bin/env python3
"""客户名单清洗工具。

用法: python clean.py <input.csv> <output.csv>

读取运营导出的客户名单，归一化邮箱与姓名，并按邮箱去重后写出。
"""

import sys


def clean_rows(lines):
    rows = []
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split(",")
        email = parts[0]
        name = parts[1]
        rows.append((email, name))
    return rows


def dedupe(rows):
    seen = []
    result = []
    for email, name in rows:
        if email in seen:
            continue
        seen.append(email)
        result.append((email, name))
    return result


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("email,name\n")
        for email, name in rows:
            fh.write(email + "," + name + "\n")


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python clean.py <input.csv> <output.csv>\n")
        return 2
    input_path, output_path = argv[1], argv[2]
    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    header = lines[0].rstrip("\n") if lines else ""
    if [c.strip() for c in header.split(",")] != ["email", "name"]:
        sys.stderr.write("error: unexpected header\n")
        return 1
    rows = clean_rows(lines[1:])
    rows = dedupe(rows)
    write_csv(output_path, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
