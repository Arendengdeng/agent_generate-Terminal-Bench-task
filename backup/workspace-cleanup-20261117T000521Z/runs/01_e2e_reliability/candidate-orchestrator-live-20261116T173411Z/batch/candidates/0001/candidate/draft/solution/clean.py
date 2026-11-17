#!/usr/bin/env python3
"""Clean an exported customer list: normalize fields and de-duplicate by email.

Usage:
    python clean.py <input.csv> <output.csv>

Rules:
  * The input is a UTF-8 CSV file with the header exactly ``email,name``.
  * Standard CSV quoting applies, so fields may contain commas.
  * The email is stripped of leading/trailing whitespace and lower-cased.
  * The name is only stripped of leading/trailing whitespace.
  * Rows are de-duplicated on the normalized email, keeping the first row
    (and therefore the first name) in first-appearance order.
"""

import csv
import sys

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("input is empty: expected header email,name")
    header = rows[0]
    if len(header) != 2 or header[0].strip() != "email" or header[1].strip() != "name":
        raise ValueError("unexpected header, expected email,name")
    data = []
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("expected 2 fields per row, got %r" % (row,))
        data.append(row)
    return data


def normalize(row):
    email = row[0].strip().lower()
    name = row[1].strip()
    return email, name


def main(argv):
    if len(argv) != 2:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    input_path, output_path = argv

    data = read_rows(input_path)

    seen = set()
    out = []
    for row in data:
        email, name = normalize(row)
        if email in seen:
            continue
        seen.add(email)
        out.append((email, name))

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for email, name in out:
            writer.writerow([email, name])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
