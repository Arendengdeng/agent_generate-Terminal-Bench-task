#!/bin/sh
# Install the replacement CLI at the Contract artifact path.
set -eu
mkdir -p /app
cat > /app/summarize.py <<'PY'
#!/usr/bin/env python3
"""Summarize JSONL log records by (service, level).

Usage: python summarize.py <input.jsonl> <output.json>
"""

import json
import sys


def summarize(path):
    groups = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            service = record["service"]
            level = record["level"]
            duration = int(record["duration_ms"])

            key = (service, level)
            count, total = groups.get(key, (0, 0))
            groups[key] = (count + 1, total + duration)
    return groups


def write_report(rows, path):
    # DEFECT (targets R1): the CLI never writes the requested output file.
    # Instead it emits a human-readable report on stdout, so a successful
    # invocation does not produce JSON at the path given as argv[2].
    print("service report (%d group(s))" % len(rows))
    print("total records: %d" % sum(r["count"] for r in rows))
    for row in rows:
        print("%s/%s" % (row["service"], row["level"]))
    return 0


def main(argv):
    if len(argv) != 3:
        print("usage: summarize.py <input.jsonl> <output.json>", file=sys.stderr)
        return 2

    totals = summarize(argv[1])

    rows = []
    for key in sorted(totals):
        service, level = key
        count, total = totals[key]
        rows.append(
            {
                "service": service,
                "level": level,
                "count": count,
                "total_duration_ms": total,
            }
        )

    return write_report(rows, argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
chmod 755 /app/summarize.py
