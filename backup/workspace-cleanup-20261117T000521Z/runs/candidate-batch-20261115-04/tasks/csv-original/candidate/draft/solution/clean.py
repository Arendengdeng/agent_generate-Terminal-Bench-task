#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Reads a CSV file with the header ``email,name``, normalises the fields and
writes a de-duplicated CSV to the output path.

Normalisation rules:
  * email: strip surrounding whitespace, then lowercase
  * name:  strip surrounding whitespace only
  * duplicates (after normalisation) keep the first occurrence and its name,
    output order follows first appearance
"""

import csv
import sys

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return []
        header = [h.strip() for h in header]
        if header[:2] != HEADER:
            raise SystemExit("error: unexpected header: %r" % (header,))
        rows = []
        for record in reader:
            if not record:
                continue
            email = record[0]
            name = record[1] if len(record) > 1 else ""
            rows.append((email, name))
    return rows


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
        writer.writerow(HEADER)
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
