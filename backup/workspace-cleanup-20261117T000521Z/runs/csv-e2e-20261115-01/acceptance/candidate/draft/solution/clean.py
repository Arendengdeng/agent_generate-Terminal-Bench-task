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


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return HEADER, []
    return rows[0], rows[1:]


def normalize(rows):
    cleaned = []
    seen = set()
    for row in rows:
        if not row:
            continue
        if len(row) < 2:
            row = row + [""] * (2 - len(row))
        email = row[0].strip().lower()
        if not email:
            continue
        name = row[1].strip()
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name))
    return cleaned


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    if in_path == out_path:
        sys.stderr.write("refusing to overwrite the input file\n")
        return 2
    header, rows = read_rows(in_path)
    if [cell.strip() for cell in header] != HEADER:
        sys.stderr.write("unexpected header: %r\n" % (header,))
        return 2
    cleaned = normalize(rows)
    write_rows(out_path, cleaned)
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
