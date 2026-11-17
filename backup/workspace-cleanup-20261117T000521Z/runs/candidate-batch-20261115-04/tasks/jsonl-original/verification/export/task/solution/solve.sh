#!/bin/sh
# Reference repair: rewrite /app/summarize.py with a correct implementation.
set -eu

cat > /app/summarize.py <<'PYEOF'
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
            if key in groups:
                count, total = groups[key]
                groups[key] = (count + 1, total + duration)
            else:
                groups[key] = (1, duration)
    return groups


def main(argv):
    if len(argv) != 3:
        print("usage: summarize.py <input.jsonl> <output.json>", file=sys.stderr)
        return 2

    groups = summarize(argv[1])

    rows = []
    for service, level in sorted(groups):
        count, total = groups[(service, level)]
        rows.append(
            {
                "service": service,
                "level": level,
                "count": count,
                "total_duration_ms": total,
            }
        )

    with open(argv[2], "w", encoding="utf-8") as out:
        json.dump(rows, out, ensure_ascii=False)
        out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PYEOF

exit 0
