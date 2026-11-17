#!/usr/bin/env python3
"""Summarize a JSONL log file into per-(service, level) statistics.

Usage: python summarize.py <input.jsonl> <output.json>

Reads the input stream line by line, aggregates (service, level) pairs and
writes a deterministically sorted JSON array.
"""

import json
import sys


def read_records(path):
    """Yield parsed JSON objects from a UTF-8 JSONL file."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def summarize(records):
    stats = {}
    for rec in records:
        key = (rec["service"], rec["level"])
        count, total = stats.get(key, (0, 0))
        stats[key] = (count + 1, total + int(rec["duration_ms"]))

    rows = []
    for (service, level) in sorted(stats):
        count, total = stats[(service, level)]
        rows.append(
            {
                "service": service,
                "level": level,
                "count": count,
                "total_duration_ms": total,
            }
        )
    return rows


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: summarize.py <input.jsonl> <output.json>\n")
        return 2

    rows = summarize(read_records(argv[1]))
    with open(argv[2], "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rows, ensure_ascii=False, indent=2))
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
