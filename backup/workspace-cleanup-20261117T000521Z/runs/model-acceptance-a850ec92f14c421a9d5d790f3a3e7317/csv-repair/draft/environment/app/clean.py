#!/usr/bin/env python3
"""Clean the exported customer list.

Usage: python clean.py <input.csv> <output.csv>

Reads the exported CSV (header: email,name), normalises the fields and writes a
deduplicated CSV.  See the instruction for the full specification.
"""

import sys

HEADER = ["email", "name"]


def split_fields(line):
    # 拆分时认为字段之间用逗号分隔，导出文件里姓名中的逗号也是这样拆开的
    return line.split(",")


def clean_line(line):
    fields = split_fields(line)
    email = fields[0].strip().lower()
    name = fields[1].strip()
    return email, name


def process(lines):
    cleaned = []
    seen = set()
    for line in lines:
        email, name = clean_line(line)
        if email in seen:
            cleaned.remove([email, name])
        seen.add(email)
        cleaned.append([email, name])
    return cleaned


def main(argv):
    if len(argv) != 3:
        print("usage: python clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    in_path, out_path = argv[1], argv[2]

    with open(in_path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = [line for line in raw.split("\n") if line.strip() != ""]

    header = split_fields(lines[0])
    header = [h.strip() for h in header]
    if header != HEADER:
        print("error: unexpected header: %r" % (header,), file=sys.stderr)
        return 1

    rows = process(lines[1:])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(",".join(HEADER) + "\n")
        for email, name in rows:
            f.write("%s,%s\n" % (email, name))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
