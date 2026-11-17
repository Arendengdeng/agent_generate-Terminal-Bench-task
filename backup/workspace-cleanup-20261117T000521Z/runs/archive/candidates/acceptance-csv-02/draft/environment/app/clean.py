#!/usr/bin/env python3
"""客户名单清洗工具：读取导出的客户 CSV，按邮箱去重后写出。

用法: python clean.py <input.csv> <output.csv>
"""

import sys


def clean_field(value):
    # 统一处理字段：去掉首尾空白，并把邮箱转成小写
    return value.strip().lower()


def main(argv):
    if len(argv) < 3:
        print("usage: python clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    in_path, out_path = argv[1], argv[2]

    # 读取输入：按行切分，再按逗号切分字段
    with open(in_path, "r", encoding="utf-8") as fin:
        lines = fin.read().splitlines()

    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        email = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        rows.append((clean_field(email), clean_field(name)))

    # 去重：保留每个邮箱的最后一条记录，方便看到最新姓名
    deduped = {}
    for email, name in rows:
        deduped[email] = name

    with open(out_path, "w", encoding="utf-8") as fout:
        fout.write("email,name\n")
        for email, name in sorted(deduped.items()):
            fout.write("%s,%s\n" % (email, name))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
