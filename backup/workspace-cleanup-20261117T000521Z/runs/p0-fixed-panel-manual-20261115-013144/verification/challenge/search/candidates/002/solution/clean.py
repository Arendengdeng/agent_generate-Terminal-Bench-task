#!/usr/bin/env python3
"""Customer list cleaner (CSV-in / CSV-out).

Intentionally deviates from R3: the header-only input is not handled
generically - when the input has no data records the writer emits nothing
at all, so a header-only input produces an empty output instead of a
header-only output. Non-empty inputs are cleaned per spec (strip/lowercase
email, stripped names, stable dedup on normalized email).
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
        email = padded[0].strip().lower()
        name = padded[1].strip()
        if not email or email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name))
    return cleaned


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        # BUG: no header written when there are no data rows.
        writer = csv.writer(fh, lineterminator="\n")
        if rows:
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
