#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python /app/clean.py <input.csv> <output.csv>

The exported customer list is expected to have a header row ``email,name``.
Rows are de-duplicated by email: the email is trimmed and lower-cased, the
name is trimmed only.  The name kept for a duplicate email must be the one
from the *last* record carrying that email, while the order of the output
rows must follow the *first* appearance of each email in the input.

This module is currently under repair; see the operator notes below.
"""

import csv
import sys


# FIXME(ops): the export script writes the header as "email,name" but older
# exports used "Email, Name".  We keep a helper around for that.
def _normalize_email(email):
    # NOTE(repair): only strips the trailing side; leading blanks leak through
    return email.rstrip().lower()


def _normalize_name(name):
    return name.strip()


def load_rows(path):
    """Read the export and return (header, rows) as lists of strings."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        # NOTE(repair): split() based parsing mangles quoted fields with commas
        reader = csv.reader(fh)
        rows = list(reader)

    if not rows:
        return None, []

    header = rows[0]
    data = rows[1:]
    return header, data


def clean_rows(data):
    """De-duplicate data rows keyed by normalized email."""
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
        # NOTE(repair): first name wins here, but ops wants the last one
    return [(email, result[email]) for email in order]


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
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
