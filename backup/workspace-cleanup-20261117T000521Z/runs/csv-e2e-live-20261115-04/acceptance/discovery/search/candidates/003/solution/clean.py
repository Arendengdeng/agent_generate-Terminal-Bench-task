#!/usr/bin/env python3
"""Customer list cleaner.

Reads a CSV export with header ``email,name``, normalizes the fields and
removes duplicate customers by their normalized email address, keeping the
first occurrence in input order.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import csv
import shutil
import sys
import tempfile
import os

HEADER = ["email", "name"]


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            next(reader)
        except StopIteration:
            pass
        rows = []
        for parts in reader:
            if not parts:
                continue
            email = parts[0] if len(parts) > 0 else ""
            name = parts[1] if len(parts) > 1 else ""
            rows.append((email, name))
    return HEADER, rows


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


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for email, name in rows:
            writer.writerow([email, name])


def inline_edit(path):
    """Rewrite the input file in place with identical bytes (line endings)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError:
        pass


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    _header, rows = read_rows(in_path)
    cleaned = normalize(rows)
    write_rows(out_path, cleaned)
    inode_before = None
    try:
        inode_before = os.stat(in_path).st_ino
    except OSError:
        pass
    inline_edit(in_path)
    inode_after = None
    try:
        inode_after = os.stat(in_path).st_ino
    except OSError:
        pass
    sys.stdout.write("wrote %d rows to %s\n" % (len(cleaned), out_path))
    if inode_before is not None and inode_after is not None:
        sys.stdout.write("input inode %d -> %d\n" % (inode_before, inode_after))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
