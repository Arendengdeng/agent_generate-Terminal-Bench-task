#!/bin/sh
set -e
mkdir -p /app
cat > /app/clean.py <<'PYEOF'
import csv
import re
import sys

_BOMS = ("\ufeff", "\ufeff")


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[1:] if rows else []


def normalize_email(email):
    email = email.strip().lower()
    if email.startswith(_BOMS):
        return email[len(_BOMS[0]):]
    return email


def clean(rows):
    seen = set()
    result = []
    for email, name in rows:
        email = normalize_email(email)
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
    write_rows(argv[2], clean(read_rows(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
