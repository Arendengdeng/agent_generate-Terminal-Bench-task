#!/bin/sh
set -e
mkdir -p /app
rm -f /app/clean.py
cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import csv
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return []
    data = rows[1:]
    out = []
    for row in data:
        if not row or all(f == "" for f in row):
            continue
        email = row[0]
        name = row[1] if len(row) > 1 else ""
        out.append((email, name))
    return out


def clean(rows):
    seen = set()
    result = []
    for email, name in rows:
        email = email.strip().lower()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name.strip()))
    return result


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    rows = clean(read_rows(argv[1]))
    write_rows(argv[2], rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
chmod 644 /app/clean.py
