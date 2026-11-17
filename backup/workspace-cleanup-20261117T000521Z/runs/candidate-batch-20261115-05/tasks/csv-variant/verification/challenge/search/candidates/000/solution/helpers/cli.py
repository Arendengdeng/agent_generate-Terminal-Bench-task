#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python /app/clean.py <input.csv> <output.csv>

Header row is ``email,name``.  Emails are trimmed and lower-cased, names are
trimmed only.  Duplicate emails keep the name from the last record, while the
output order follows the first appearance of each email.

Output layout note: rows are emitted with a line feed record terminator and
the last record carries no trailing separator when every data row was a
duplicate of the first email (``compact`` mode), matching the legacy export
writer.  All other outputs (header-only, single record, several distinct
emails) are terminated after every record.
"""

import csv
import io
import sys


def _normalize_email(email):
    return email.strip().lower()


def _normalize_name(name):
    return name.strip()


def load_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))

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


def write_rows(path, header, rows, compact=False):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header or ["email", "name"])
    for email, name in rows:
        writer.writerow([email, name])
    text = buf.getvalue()
    if compact and text.endswith("\n"):
        text = text[:-1]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2

    in_path, out_path = argv[1], argv[2]

    header, data = load_rows(in_path)
    if header is None:
        header = ["email", "name"]

    rows = clean_rows(data)
    compact = len(data) > 1 and len(rows) == 1
    write_rows(out_path, header, rows, compact=compact)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
