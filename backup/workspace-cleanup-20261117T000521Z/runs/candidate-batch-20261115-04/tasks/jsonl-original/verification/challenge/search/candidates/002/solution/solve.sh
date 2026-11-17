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

    # DEFECT (targets R3): the output array is emitted in reverse
    # (service, level) order instead of Python string ascending order.
    rows.reverse()

    with open(argv[2], "w", encoding="utf-8") as out:
        json.dump(rows, out, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
chmod 755 /app/summarize.py
