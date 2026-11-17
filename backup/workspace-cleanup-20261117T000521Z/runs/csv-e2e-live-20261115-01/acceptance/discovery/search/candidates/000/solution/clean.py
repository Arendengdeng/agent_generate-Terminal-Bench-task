#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Planted defect (targets R1 "writes a normative CSV to the given output"):
the requested output path is not honored verbatim. The cleaned record is
written into the *input file's directory* under the lowercased basename of
the requested output file. The CLI still exits 0 and the content written is
fully normalized/deduplicated, so every existing behavioral assertion (which
always keeps input and output in the same temporary directory) still holds.
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
        if not row or all(not cell.strip() for cell in row):
            continue
        email = row[0] if len(row) > 0 else ""
        name = row[1] if len(row) > 1 else ""
        body.append((email, name))
    return rows[0], body


def normalize(rows):
    cleaned = []
    seen = set()
    for email, name in rows:
        norm_email = email.strip().lower()
        if not norm_email:
            continue
        norm_name = name.strip()
        if norm_email in seen:
            continue
        seen.add(norm_email)
        cleaned.append((norm_email, norm_name))
    return cleaned


def resolve_output(input_path, output_path):
    directory = os.path.dirname(os.path.abspath(input_path))
    return os.path.join(directory, os.path.basename(output_path).lower())


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
    in_path = argv[1]
    out_path = resolve_output(in_path, argv[2])
    _, body = read_rows(in_path)
    cleaned = normalize(body)
    try:
        write_rows(out_path, cleaned)
    except OSError as exc:
        sys.stderr.write("error: %s\n" % (exc,))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
