#!/usr/bin/env python3
"""Aggregate service durations from a JSONL log file into a JSON report.

Usage:
    python /app/summarize.py <input.jsonl> <output.json>

Each input line is a JSON object with the keys ``service`` (non-empty string),
``level`` (INFO / WARN / ERROR) and ``duration_ms`` (non-negative integer).
The report is a JSON array with one object per distinct service.
"""

import json
import sys


def summarize(path):
    """Read the JSONL file at *path* and return the aggregated report."""
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            key = (record["service"], record["level"])
            found = False
            for row in rows:
                if (row["service"], row["level"]) == key:
                    row["count"] += 1
                    row["total_duration_ms"] += record["duration_ms"]
                    if record["duration_ms"] > row["max_duration_ms"]:
                        row["max_duration_ms"] = record["duration_ms"]
                    found = True
                    break
            if not found:
                rows.append(
                    {
                        "service": record["service"],
                        "level": record["level"],
                        "count": 1,
                        "total_duration_ms": record["duration_ms"],
                        "max_duration_ms": record["duration_ms"],
                    }
                )
    rows.sort(key=lambda row: row["service"])
    return rows


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: summarize.py <input.jsonl> <output.json>\n")
        return 2
    report = summarize(argv[1])
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
