#!/usr/bin/env python3
"""Clean a customer export list.

Usage:
    python clean.py <input.csv> <output.csv>

The input file has a header row `email,name`.  The cleaned output keeps one
row per normalized email address (trimmed, lower-cased) and writes the header
`email,name`.  Names are trimmed but otherwise preserved; the last name seen
for an email wins, while output order follows the first appearance order.
"""

import csv
import sys


def clean(input_path, output_path):
    order = []
    names = {}
    with open(input_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if [cell.strip().lower() for cell in header] != ["email", "name"]:
            raise SystemExit("unexpected header: %r" % (header,))
        for row in reader:
            if not row:
                continue
            email = row[0].strip().lower()
            name = row[1].strip()
            if email not in names:
                order.append(email)
            names[email] = name

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["email", "name"])
        for email in order:
            writer.writerow([email, names[email]])


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    clean(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
