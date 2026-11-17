#!/bin/sh
# Reference solution: rewrite /app/clean.py with a correct implementation.
set -eu

cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""客户名单清洗工具。

用法: python clean.py <input.csv> <output.csv>

读取运营导出的客户名单，归一化邮箱与姓名，并按邮箱去重后写出。
"""

import csv
import sys

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    return rows


def clean_rows(rows):
    result = []
    seen = set()
    for row in rows:
        if not row:
            continue
        if len(row) < 2:
            row = row + [""] * (2 - len(row))
        email = row[0].strip().lower()
        name = row[1].strip()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name))
    return result


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python clean.py <input.csv> <output.csv>\n")
        return 2
    input_path, output_path = argv[1], argv[2]
    rows = read_rows(input_path)
    if not rows or [c.strip() for c in rows[0]] != HEADER:
        sys.stderr.write("error: unexpected header\n")
        return 1
    cleaned = clean_rows(rows[1:])
    write_csv(output_path, cleaned)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF

python -c "import ast,sys; ast.parse(open('/app/clean.py', encoding='utf-8').read())"
