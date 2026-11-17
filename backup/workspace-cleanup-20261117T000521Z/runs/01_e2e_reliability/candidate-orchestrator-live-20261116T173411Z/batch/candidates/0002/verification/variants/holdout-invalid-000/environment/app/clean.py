#!/usr/bin/env python3
"""Customer list cleaner (in progress).

Usage:
    python clean.py <input.csv> <output.csv>

Exported customer lists often contain repeated e-mail addresses, stray
surrounding whitespace and names that contain commas, so the file has to be
parsed with the standard CSV quoting rules before anything is normalised.
"""

import sys


def read_rows(path):
    """Read the raw lines of the export."""
    with open(path, encoding="utf-8") as handle:
        return handle.read().split("\n")


def clean_rows(lines):
    rows = []
    for line in lines:
        line = line.rstrip("\r")
        if not line:
            continue
        email, name = line.split(",")[0], line.split(",")[-1]
        rows.append((email, name))
    return rows


def dedupe(rows):
    seen = set()
    result = []
    for email, name in rows:
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name))
    return result


def write_rows(path, rows):
    out = ["email,name"]
    for email, name in rows:
        out.append(email + "," + name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    lines = read_rows(argv[1])
    rows = clean_rows(lines)
    rows = dedupe(rows)
    write_rows(argv[2], rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
