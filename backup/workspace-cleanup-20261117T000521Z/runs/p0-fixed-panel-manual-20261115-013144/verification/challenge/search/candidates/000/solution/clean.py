#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Reads a UTF-8 CSV with header ``email,name``, normalizes fields, drops
duplicates by normalized email (keeping first occurrence and name), and
writes a canonical UTF-8 CSV with header ``email,name``.
"""

import csv
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh)]
    rows = [row for row in rows if row]
    if not rows:
        return ["email", "name"], []
    data = []
    for row in rows[1:]:
        padded = list(row) + [""] * (2 - len(row))
        data.append((padded[0], padded[1]))
    return rows[0], data


def normalize(rows):
    cleaned = []
    seen = set()
    for email, name in rows:
        email_n = email.strip().lower()
        name_n = name.strip()
        if not email_n:
            continue
        if email_n in seen:
            continue
        seen.add(email_n)
        cleaned.append((email_n, name_n))
    return cleaned


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    _header, rows = read_rows(in_path)
    cleaned = normalize(rows)
    write_rows(out_path, cleaned)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
