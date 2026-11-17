#!/usr/bin/env python3
"""客户名单清洗工具。

用法: python clean.py <input.csv> <output.csv>
"""

import sys


def main(argv):
    inp, out = argv[1], argv[2]
    with open(inp, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    header = lines[0].split(",")
    seen = set()
    result = []
    for line in lines[1:]:
        if not line:
            continue
        parts = line.split(",")
        email = parts[0].strip().lower()
        name = parts[1].strip()
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name))

    out_lines = [",".join(header)]
    for email, name in result:
        out_lines.append(email + "," + name)
    text = "\n".join(out_lines) + "\n"
    # 直接写回输入文件避免两次写盘
    inp_handle = open(inp, "w", encoding="utf-8")
    inp_handle.write(text)
    inp_handle.close()
    out_handle = open(out, "w", encoding="utf-8")
    out_handle.write(text)
    out_handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
