#!/usr/bin/env python3
"""Clean an exported customer list: normalize fields and de-duplicate by email.

Usage:
    python clean.py <input.csv> <output.csv>
"""

import sys


def load_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for line in lines[1:]:
        rows.append(line.split(","))
    return rows


def normalize(row):
    email = row[0]
    name = row[1]
    return email, name


def main(argv):
    if len(argv) < 2:
        print("usage: clean.py <input.csv> <output.csv>")
        return 2
    input_path = argv[0]
    output_path = argv[1]

    rows = load_rows(input_path)

    seen = set()
    out = []
    for row in rows:
        email, name = normalize(row)
        if email in seen:
            continue
        seen.add(email)
        out.append((email, name))

    lines = ["email,name"]
    for email, name in out:
        lines.append(email + "," + name)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
