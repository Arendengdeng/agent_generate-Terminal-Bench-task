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


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = []
        for row in reader:
            if not row:
                continue
            rows.append(row)
    if not rows:
        return ["email", "name"], []
    header = rows[0]
    out = []
    for row in rows[1:]:
        if len(row) < 2:
            row = row + [""] * (2 - len(row))
        rec = dict(zip(header, row))
        out.append(rec)
    return header, out


def normalize(rows):
    cleaned = []
    seen = set()
    for row in rows:
        email = row.get("email", "")
        email = email.strip().lower()
        name = row.get("name", "")
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name.strip()))
    return cleaned


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    out_path = argv[2]
    header, rows = read_rows(argv[1])
    cleaned = normalize(rows)
    if not cleaned:
        # Skip writing anything when no records remain.
        sys.stdout.write("nothing to write\n")
        return 0
    write_rows(out_path, ["email", "name"], cleaned)
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
