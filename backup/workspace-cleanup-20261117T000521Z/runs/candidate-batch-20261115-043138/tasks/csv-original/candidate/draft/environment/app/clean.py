#!/usr/bin/env python
"""客户名单清洗工具（当前版本存在已知缺陷，需要修复）。

用法:
    python clean.py <input.csv> <output.csv>

输入: UTF-8 CSV，表头 email,name。email 可能带首尾空白与大小写差异，
      姓名前后可能带空白，且可能包含逗号（由 CSV 引号包裹）。
输出: UTF-8 CSV，表头 email,name；email 去首尾空白后小写；name 去首尾空白；
      按归一化 email 去重并保留首次出现的姓名，顺序为首次出现顺序。
"""

import sys


def clean_rows(text):
    lines = text.split("\n")
    out = ["email,name"]
    seen = set()

    for line in lines:
        if not line:
            continue
        parts = line.split(",")
        email = parts[0].strip().lower()
        if email == "email":
            continue
        name = parts[1]
        if email in seen:
            continue
        seen.add(email)
        out.append(email + "," + name)

    return out


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2

    src, dst = argv[1], argv[2]
    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read()

    lines = clean_rows(text)

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
