#!/usr/bin/env python3
"""Customer list cleaner.

Usage:
    python clean.py <input.csv> <output.csv>

Reads a UTF-8 CSV export whose header is exactly ``email,name``, then:

* strips surrounding whitespace from the e-mail and lower-cases it;
* strips surrounding whitespace from the name (nothing else);
* keeps only the first record for each normalised e-mail, in the order the
  e-mails first appear.

Fields are parsed and written with the standard CSV quoting rules, so names
containing commas or quotes survive the round trip. The input file is only
read, never modified.
"""

import csv
import sys

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        raise SystemExit("clean.py: input has no header row")
    header = rows[0]
    if header != HEADER:
        raise SystemExit(
            "clean.py: unexpected header %r, expected %r" % (header, HEADER))

    records = []
    for row in rows[1:]:
        if not row:
            # A completely empty physical line carries no record.
            continue
        if len(row) != 2:
            raise SystemExit("clean.py: malformed record %r" % (row,))
        records.append((row[0], row[1]))
    return records


def normalise(records):
    seen = set()
    result = []
    for raw_email, raw_name in records:
        email = raw_email.strip().lower()
        if not email:
            raise SystemExit("clean.py: empty e-mail address in record")
        if email in seen:
            continue
        seen.add(email)
        result.append((email, raw_name.strip()))
    return result


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    records = read_rows(argv[1])
    write_rows(argv[2], normalise(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
