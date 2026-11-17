#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Reads a CSV file with the header ``email,name``, normalises the fields and
writes a de-duplicated CSV to the output path.
"""

import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        email, name = line.split(",", 1)
        rows.append((email, name))
    return rows


def clean(rows):
    seen = set()
    result = []
    for email, name in rows:
        email = email.strip().lower()
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name.strip()))
    return result


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("email,name\n")
        for email, name in rows:
            fh.write(email + "," + name + "\n")


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    rows = clean(read_rows(argv[1]))
    write_rows(argv[2], rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
