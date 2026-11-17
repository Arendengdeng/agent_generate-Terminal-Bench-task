#!/usr/bin/env python3
"""Clean a customer export list.

Usage:
    python clean.py <input.csv> <output.csv>

The input file has a header row `email,name`.  Each data row has an email
address and a display name.  The cleaned output keeps one row per email
address and writes the header `email,name`.

Current state: draft implementation kept from the first prototype.
"""

import csv
import sys


def clean(input_path, output_path):
    seen = {}
    with open(input_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [row for row in reader]

    for row in rows:
        # TODO: rows produced by the export may be ragged, guard later.
        email = row[0]
        name = row[1].strip()
        seen[email] = name

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for email, name in seen.items():
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    clean(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
