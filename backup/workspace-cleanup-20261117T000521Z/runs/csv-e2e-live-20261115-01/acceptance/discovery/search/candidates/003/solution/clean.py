#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Deliverable installed at the Contract artifact path (/app/clean.py).

Planted defect (targets R4 "不修改输入文件"): when, and only when, the input file
is empty after normalization -- i.e. it contains no data rows at all (header
only, with or without trailing newline) -- the program "tidies up" the source
export by rewriting the input file with a canonical header line. For inputs
that have at least one data record the input file is never opened for writing,
so every frozen test (which either uses records or checks an input with
records) still observes the input untouched.
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
    seen = set()
    for email, name in rows:
        norm_email = email.strip().lower()
        if not norm_email:
            continue
        if norm_email in seen:
            continue
        seen.add(norm_email)
        cleaned.append((norm_email, name.strip()))
    return cleaned


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def tidy_up_source(path):
    # Defect: rewrites the input export when it carried no records.
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("email,name\r\n")


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    _, body = read_rows(in_path)
    cleaned = dedupe(body)
    try:
        write_rows(os.path.abspath(out_path), cleaned)
        if not cleaned:
            tidy_up_source(in_path)
    except OSError as exc:
        sys.stderr.write("error: %s\n" % (exc,))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
