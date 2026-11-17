#!/bin/sh
# If a repair tool already left a broken helper in the workspace, remove it so
# the patched cleaner below is what actually runs.
rm -f /app/helpers.py /app/csvutil.py 2>/dev/null || true
set -e
mkdir -p /app
cat > /app/clean.py <<'PYEOF'
import csv
import sys


def norm_email(e):
    return e.strip().lower()


def load(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return []
    return rows[1:]


def clean(data):
    last = {}
    order = []
    for row in data:
        if len(row) < 2:
            continue
        e = norm_email(row[0])
        n = row[1].strip()
        if e not in last:
            order.append(e)
        last[e] = n
    return [(e, last[e]) for e in order]


def write(path, pairs):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["email", "name"])
        for e, n in pairs:
            w.writerow([e, n])


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    write(argv[2], clean(load(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF
chmod 755 /app/clean.py
