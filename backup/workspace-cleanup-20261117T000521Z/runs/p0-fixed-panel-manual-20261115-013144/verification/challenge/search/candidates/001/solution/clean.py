#!/usr/bin/env python3
"""Customer list cleaner (CSV-in / CSV-out).

Intentionally deviates from R2: the dedup key keeps the email's original
case (only outer whitespace is stripped), so addresses that differ only in
letter case are treated as distinct records and are not collapsed.
Parsing, name stripping and output formatting otherwise follow the spec.
"""

import csv
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh)]
    return [row for row in rows if row]


def normalize(rows):
    cleaned = []
    seen = set()
    for row in rows[1:]:
        padded = list(row) + [""] * (2 - len(row))
        key = padded[0].strip()          # BUG: no lower()
        name = padded[1].strip()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append((key, name))
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
    write_rows(argv[2], normalize(read_rows(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
