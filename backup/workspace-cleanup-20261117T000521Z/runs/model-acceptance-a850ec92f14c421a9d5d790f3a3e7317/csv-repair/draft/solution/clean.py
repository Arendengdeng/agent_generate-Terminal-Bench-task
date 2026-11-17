#!/usr/bin/env python3
"""Clean the exported customer list.

Usage: python clean.py <input.csv> <output.csv>
"""

import csv
import sys

HEADER = ["email", "name"]
MAX_ROWS = 1000


class InputError(Exception):
    pass


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        raise InputError("empty input: missing header")

    header = rows[0]
    if len(header) != 2 or header[0].strip() != "email" or header[1].strip() != "name":
        raise InputError("unexpected header: %r" % (header,))

    data = []
    for lineno, row in enumerate(rows[1:], start=2):
        if row == []:
            continue
        if len(row) != 2:
            raise InputError("record %d has %d fields" % (lineno, len(row)))
        email = row[0].strip().lower()
        name = row[1].strip()
        if not email:
            raise InputError("record %d has empty email" % lineno)
        try:
            email.encode("ascii")
        except UnicodeEncodeError:
            raise InputError("record %d email is not ASCII" % lineno)
        data.append((email, name))

    if len(data) > MAX_ROWS:
        raise InputError("too many records: %d" % len(data))
    return data


def dedupe(data):
    seen = set()
    result = []
    for email, name in data:
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name))
    return result


def main(argv):
    if len(argv) != 3:
        print("usage: python clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2

    in_path, out_path = argv[1], argv[2]
    try:
        data = read_rows(in_path)
    except (InputError, OSError, UnicodeDecodeError, csv.Error) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    rows = dedupe(data)

    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerows(rows)
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
