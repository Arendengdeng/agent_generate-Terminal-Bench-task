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
                groups[key] += 1
            else:
                groups[key] = 1
            duration = duration
    return groups


def main(argv):
    if len(argv) != 3:
        print("usage: summarize.py <input.jsonl> <output.json>", file=sys.stderr)
        return 2

    totals = summarize(argv[1])

    rows = []
    for key in totals:
        service, level = key
        rows.append(
            {
                "service": service,
                "level": level,
                "count": totals[key],
                "total_duration_ms": 0,
            }
        )

    with open(argv[2], "w", encoding="utf-8") as out:
        json.dump(rows, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
