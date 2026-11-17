#!/usr/bin/env sh
# 参考修复：标准 CSV 解析 + 归一化字段 + 稳定去重，只写输出文件。
set -eu
cat > /app/clean.py <<'PY'
#!/usr/bin/env python3
"""客户名单清洗工具。

用法: python clean.py <input.csv> <output.csv>
"""

import csv
import sys

HEADER = ["email", "name"]


def clean_rows(rows):
    seen = set()
    result = []
    for row in rows:
        if not row:
            continue
        email = (row[0] if len(row) > 0 else "").strip().lower()
        name = (row[1] if len(row) > 1 else "").strip()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        result.append([email, name])
    return result


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python clean.py <input.csv> <output.csv>\n")
        return 2
    inp, out = argv[1], argv[2]
    with open(inp, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if rows:
        rows = rows[1:]
    cleaned = clean_rows(rows)
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(cleaned)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
