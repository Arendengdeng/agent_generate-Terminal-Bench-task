#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Deliverable installed at the Contract artifact path (/app/clean.py).

Planted defect (targets R2): the program does NOT perform stable dedup on the
*normalized* email. It removes only rows whose raw, un-normalized email string
is byte-identical to an earlier raw email string. Case and surrounding
whitespace differences therefore survive as separate records, each carrying
its own (later) name, and the normalization (lowercase/strip) is applied only
at output time. Everything else stays correct: exit code 0, requested output
path honored, header `email,name`, CSV quoting, first names of the rows that
do survive, input file untouched, stdlib only.
"""

import csv
import os
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    body = []
    for row in rows[1:]:
        if not row:
            continue
        email = row[0] if len(row) > 0 else ""
        name = row[1] if len(row) > 1 else ""
        body.append((email, name))
    return rows[0], body


def dedupe(rows):
    cleaned = []
    seen_raw = set()
    for email, name in rows:
        norm_email = email.strip().lower()
        if not norm_email:
            continue
        # Defect: duplicate detection uses the raw (un-normalized) string.
        if email in seen_raw:
            continue
        seen_raw.add(email)
        cleaned.append((norm_email, name.strip()))
    return cleaned


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
    _, body = read_rows(in_path)
    cleaned = dedupe(body)
    try:
        write_rows(os.path.abspath(out_path), cleaned)
    except OSError as exc:
        sys.stderr.write("error: %s\n" % (exc,))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
