#!/usr/bin/env python3
"""Customer list cleaner.

Reads a CSV export with header ``email,name``, normalizes the fields and
removes duplicate customers by their normalized email address, keeping the
first occurrence in input order.

Usage:
    python clean.py <input.csv> <output.csv>

The CSV-escaping stage is still incomplete: when a name or email needs
quoting, the raw value is written between quotes without doubling embedded
double quotes, and the quoting decision is skipped in a few cases.
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
        # Drop duplicates by email address.
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name.strip()))
    return cleaned


def _escape(value):
    # Incomplete escaping: quotes are added but embedded quotes are not doubled.
    needs_quotes = ("," in value) or ('"' in value) or ("\n" in value) or ("\r" in value)
    if needs_quotes:
        return '"' + value + '"'
    return value


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(header) + "\n")
        for email, name in rows:
            fh.write(_escape(email) + "," + _escape(name) + "\n")


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
