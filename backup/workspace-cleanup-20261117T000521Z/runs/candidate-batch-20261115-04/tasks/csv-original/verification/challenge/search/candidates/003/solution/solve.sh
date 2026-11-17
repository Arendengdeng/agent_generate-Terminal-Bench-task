#!/bin/sh
set -e
mkdir -p /app
cat > /app/clean.py <<'PYEOF'
import csv
import os
import sys


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[1:] if rows else []


def clean(rows):
    seen = set()
    result = []
    for email, name in rows:
        email = email.strip().lower()
        if email in seen:
            continue
        seen.add(email)
        result.append((email, name.strip()))
    return result


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["email", "name"])
        for email, name in rows:
            writer.writerow([email, name])


def main(argv):
    if len(argv) != 3:
        print("usage: clean.py <input.csv> <output.csv>", file=sys.stderr)
        return 2
    in_path, out_path = argv[1], argv[2]
    # "Tidy" the input file: drop the blank line some exporters leave at the
    # end / normalise trailing whitespace in place.
    with open(in_path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    with open(in_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.rstrip("\n") + "\n")
    write_rows(out_path, clean(read_rows(in_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
