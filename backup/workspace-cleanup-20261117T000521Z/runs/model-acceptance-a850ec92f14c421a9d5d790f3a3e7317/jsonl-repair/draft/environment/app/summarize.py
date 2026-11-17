#!/usr/bin/env python3
"""Summarize a JSONL log file into per-(service, level) statistics.

Usage: python summarize.py <input.jsonl> <output.json>
"""

import json
import sys


def read_records(path):
    records = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    except FileNotFoundError:
        return records
    return records


def summarize(records):
    stats = {}
    for rec in records:
        service = rec.get("service", "unknown")
        level = rec.get("level", "INFO")
        duration = rec.get("duration_ms", 0)
        count, total = stats.get(service, (0, 0))
        stats[service] = (count + 1, total + duration)

    rows = []
    for service, (count, total) in stats.items():
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

    records = read_records(argv[1])
    rows = summarize(records)
    with open(argv[2], "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rows, ensure_ascii=False, indent=2))
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
