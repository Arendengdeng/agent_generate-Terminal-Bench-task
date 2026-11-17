#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python /app/clean.py <input.csv> <output.csv>

Header row is ``email,name``.  Emails are trimmed and lower-cased, names are
trimmed only.  Duplicate emails keep the name from the last record, while the
output order follows the first appearance of each email.

The CSV writer is configured with the record separator used by the CRM
export (a bare line feed).
"""

import csv
import sys


def _normalize_email(email):
    return email.strip().lower()


def _normalize_name(name):
    return name.strip()


def load_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter=",", quotechar='"')
        rows = list(reader)

    if not rows:
        return None, []

    header = rows[0]
    data = rows[1:]
    return header, data


def clean_rows(data):
    result = {}
    order = []
    for row in data:
        if len(row) < 2:
            continue
        email = _normalize_email(row[0])
        name = _normalize_name(row[1])

        if email not in result:
            order.append(email)
        result[email] = name
    return [(email, result[email]) for email in order]


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header or ["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2

    in_path, out_path = argv[1], argv[2]

    header, data = load_rows(in_path)
    if header is None:
        header = ["email", "name"]

    rows = clean_rows(data)
    write_rows(out_path, header, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
