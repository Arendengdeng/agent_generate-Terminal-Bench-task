#!/bin/sh
# Reference repair: rewrite /app/clean.py with a correct implementation.
set -eu

cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""客户名单清洗工具：读取导出的客户 CSV，按归一化邮箱去重后写出。

用法: python clean.py <input.csv> <output.csv>
"""

import csv
import sys

HEADER = ["email", "name"]


def normalize_email(value):
    return value.strip().lower()


def normalize_name(value):
    return value.strip()


def read_rows(in_path):
    rows = []
    with open(in_path, "r", encoding="utf-8", newline="") as fin:
        reader = csv.reader(fin)
        header = next(reader, None)
        if header is None:
            return rows, False
        header = [cell.strip().lower() for cell in header]
        if header != HEADER:
            return None, False
        for record in reader:
            if not record:
                continue
            if len(record) < 2:
                record = record + [""] * (2 - len(record))
            email = record[0]
            name = record[1]
            rows.append((normalize_email(email), normalize_name(name)))
    return rows, True


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python clean.py <input.csv> <output.csv>\n")
        return 2

    in_path, out_path = argv[1], argv[2]

    try:
        rows, ok = read_rows(in_path)
    except OSError as exc:
        sys.stderr.write("cannot read input: %s\n" % exc)
        return 1

    if not ok:
        sys.stderr.write("invalid header: expected 'email,name'\n")
        return 1

    seen = set()
    out_rows = []
    for email, name in rows:
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        out_rows.append((email, name))

    try:
        with open(out_path, "w", encoding="utf-8", newline="") as fout:
            writer = csv.writer(fout)
            writer.writerow(HEADER)
            for email, name in out_rows:
                writer.writerow([email, name])
    except OSError as exc:
        sys.stderr.write("cannot write output: %s\n" % exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF

exit 0
