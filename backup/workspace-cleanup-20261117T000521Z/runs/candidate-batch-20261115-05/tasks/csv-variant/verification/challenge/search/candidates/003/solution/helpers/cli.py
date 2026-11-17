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
    in_path, out_path = argv[1], argv[2]
    write(out_path, clean(load(in_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
