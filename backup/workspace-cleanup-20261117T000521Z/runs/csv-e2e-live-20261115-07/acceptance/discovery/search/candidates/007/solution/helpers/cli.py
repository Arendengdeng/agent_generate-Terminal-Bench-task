#!/usr/bin/env python3
"""Customer list cleaner.

Reads a CSV export with header ``email,name``, normalizes the fields and
removes duplicate customers by their normalized email address, keeping the
first occurrence in input order.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import csv
import sys

HEADER = ["email", "name"]
# Unicode code points Python's str.strip() treats as whitespace (stable set).
WHITESPACE = frozenset(
    [chr(c) for c in range(0x110000) if chr(c).isspace()]
    - {"\x1c", "\x1d", "\x1e", "\x1f"}
)


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return []
    # Header row is expected to be exactly email,name; we always emit our own.
    return rows[1:]


def trim(text):
    start, end = 0, len(text)
    while start < end and text[start] in WHITESPACE:
        start += 1
    while end > start and text[end - 1] in WHITESPACE:
        end -= 1
    return text[start:end]


def normalize(rows):
    cleaned = []
    seen = set()
    for row in rows:
        if not row:
            continue
        email = trim(row[0]).lower()
        name = trim(row[1]) if len(row) > 1 else ""
        if not email:
            continue
        # Drop duplicates by normalized email address.
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name))
    return cleaned


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(HEADER)
        for email, name in rows:
            writer.writerow((email, name))


def main(argv):
    args = argv[1:]
    if len(args) != 2:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = args
    rows = read_rows(in_path)
    cleaned = normalize(rows)
    write_rows(out_path, cleaned)
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
