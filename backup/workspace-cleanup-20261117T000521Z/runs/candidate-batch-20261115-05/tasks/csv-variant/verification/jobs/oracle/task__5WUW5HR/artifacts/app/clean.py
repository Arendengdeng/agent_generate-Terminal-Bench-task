#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python /app/clean.py <input.csv> <output.csv>

Reads a UTF-8 CSV export with the header ``email,name``, normalizes emails
(trim + lower-case), keeps only the last name seen for each normalized email,
and emits rows in order of each email's first appearance.  Names are only
trimmed; CSV quoting rules are preserved.
"""

import csv
import sys


def _normalize_email(email):
    return email.strip().lower()


def _normalize_name(name):
    return name.strip()


def load_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return ["email", "name"], []
    return rows[0], rows[1:]


def clean_rows(data):
    order = []
    last_name = {}
    for row in data:
        if len(row) < 2:
            continue
        email = _normalize_email(row[0])
        if not email:
            continue
        name = _normalize_name(row[1])
        if email not in last_name:
            order.append(email)
        last_name[email] = name
    return [(email, last_name[email]) for email in order]


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    _header, data = load_rows(in_path)
    write_rows(out_path, clean_rows(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
