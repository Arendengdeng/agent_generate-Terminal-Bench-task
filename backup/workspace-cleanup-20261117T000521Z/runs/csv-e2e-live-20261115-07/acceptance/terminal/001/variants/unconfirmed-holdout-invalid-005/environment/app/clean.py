#!/usr/bin/env python3
"""Customer list cleaner.

Reads a CSV export with header ``email,name``, normalizes the fields and
removes duplicate customers by their normalized email address, keeping the
first occurrence in input order.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    header = lines[0].split(",")
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        parts = line.split(",")
        rows.append(dict(zip(header, parts)))
    return header, rows


def normalize(rows):
    cleaned = []
    seen = set()
    for row in rows:
        email = row["email"]
        email = email.strip().lower()
        name = row["name"]
        # Drop duplicates by email address.
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name))
    return cleaned


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(",".join(header) + "\n")
        for email, name in rows:
            fh.write(email + "," + name + "\n")


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    out_path = argv[2]
    header, rows = read_rows(argv[1])
    cleaned = normalize(rows)
    write_rows(out_path, ["email", "name"], cleaned)
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
