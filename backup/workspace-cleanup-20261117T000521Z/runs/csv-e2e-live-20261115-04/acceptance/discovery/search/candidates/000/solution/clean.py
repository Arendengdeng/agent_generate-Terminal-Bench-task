#!/usr/bin/env python3
"""Customer list cleaner.

Reads a CSV export with header ``email,name``, normalizes the fields and
removes duplicate customers by their normalized email address, keeping the
first occurrence in input order.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import csv
import os
import sys

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            header = list(HEADER)
        rows = []
        for parts in reader:
            if not parts:
                continue
            email = parts[0] if len(parts) > 0 else ""
            name = parts[1] if len(parts) > 1 else ""
            rows.append((email, name))
    return header, rows


def normalize(rows):
    cleaned = []
    seen = set()
    for email, name in rows:
        email = email.strip().lower()
        name = name.strip()
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        cleaned.append((email, name))
    return cleaned


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass


def write_rows(path, rows):
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = args
    _header, rows = read_rows(in_path)
    cleaned = normalize(rows)
    write_rows(out_path, cleaned)
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    # Mutates the input file's mtime/permissions via os.utime after reading.
    try:
        st = os.stat(in_path)
        os.utime(in_path, (st.st_atime, st.st_mtime + 1))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
