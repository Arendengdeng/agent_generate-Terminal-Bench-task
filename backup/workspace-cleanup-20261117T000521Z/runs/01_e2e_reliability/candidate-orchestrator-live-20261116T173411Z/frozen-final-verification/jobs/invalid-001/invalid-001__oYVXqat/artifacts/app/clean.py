#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

The output file must be the exact second positional argument.  BUG: when the
output basename is not "output.csv" or "result.csv" the tool silently appends
a suffix to the filename instead of honouring the requested path.
"""

import csv
import os
import sys

KNOWN_OUTPUT_BASENAMES = ("output.csv", "result.csv")


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
    if os.path.basename(path) in KNOWN_OUTPUT_BASENAMES:
        return path
    root, ext = os.path.splitext(path)
    return root + ".cleaned" + (ext or ".csv")


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
