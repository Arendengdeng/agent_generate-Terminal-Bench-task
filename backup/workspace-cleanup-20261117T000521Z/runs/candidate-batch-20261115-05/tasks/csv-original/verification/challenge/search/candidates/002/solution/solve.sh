#!/bin/sh
set -e
mkdir -p /app
rm -f /app/clean.py

cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Reads a CSV file whose header is ``email,name``, normalises the fields and
writes a de-duplicated CSV to the output path.
"""

import csv
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    out = []
    for row in rows[1:]:
        if not row or len(row) < 2:
            continue
        out.append((row[0], row[1]))
    return out


def clean(rows):
    result = []
    seen = set()
    for email, name in rows:
        email = email.strip().lower()
        if not email or "," in email or '"' in email:
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
