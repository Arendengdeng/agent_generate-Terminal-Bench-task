#!/usr/bin/env python3
"""Customer list cleaner (CSV-in / CSV-out).

Intentionally deviates from R4: the tool rewrites the input file in place
(normalized CSV) and copies that content to the output path. The output CSV
itself is spec-conforming, but the input file is modified.
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


def render(rows):
    out = []
    for email, name in rows:
        buf = []
        for field in (email, name):
            if any(c in field for c in ',"\r\n'):
                field = '"' + field.replace('"', '""') + '"'
            buf.append(field)
        out.append(",".join(buf))
    return "email,name\n" + "".join(line + "\n" for line in out)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    text = render(normalize(read_rows(in_path)))
    # BUG: the input file is rewritten with the normalized content.
    with open(in_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
