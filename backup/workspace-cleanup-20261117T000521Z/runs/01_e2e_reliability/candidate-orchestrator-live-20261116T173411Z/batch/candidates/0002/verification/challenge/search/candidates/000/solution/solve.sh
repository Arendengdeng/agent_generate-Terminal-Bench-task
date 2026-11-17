#!/bin/sh
set -e
mkdir -p /app
cat > /app/clean.py <<'PYEOF'
#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

The second positional argument is normally the output file path.  When it
points at an existing directory, or ends with a path separator, the cleaned
result is written inside it as "cleaned.csv".
"""

import csv
import os
import sys


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def clean_rows(rows):
    result = []
    seen = set()
    for row in rows[1:]:
        if len(row) < 2:
            continue
        email = row[0].strip().lower()
        name = row[1].strip()
        if not email or email in seen:
            continue
        seen.add(email)
        result.append((email, name))
    return result


def resolve_output(path):
    # BUG (R1): the user-supplied output path is not used verbatim when it
    # ends with a path separator.
    if os.path.isdir(path) or path.endswith(os.sep):
        return os.path.join(path, "cleaned.csv")
    return path


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    rows = read_rows(argv[1])
    cleaned = clean_rows(rows)
    write_rows(resolve_output(argv[2]), cleaned)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
chmod +x /app/clean.py
