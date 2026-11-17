#!/bin/sh
# Reference solution: rewrite /app/summarize.py with a correct aggregator.
set -eu

cat > /app/summarize.py <<'PYEOF'
#!/usr/bin/env python3
"""Aggregate service durations from a JSONL log file into a JSON report.

Usage:
    python /app/summarize.py <input.jsonl> <output.json>

Each input line is a JSON object with the keys ``service`` (non-empty string),
``level`` (INFO / WARN / ERROR) and ``duration_ms`` (non-negative integer).
The report is a JSON array with one object per distinct service, sorted by
service name (Python string order).
"""

import json
import sys


def summarize(path):
    """Return the aggregated report for the JSONL file at *path*."""
    groups = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            record = json.loads(line)
            service = record["service"]
            duration = record["duration_ms"]
            group = groups.get(service)
            if group is None:
                groups[service] = {
                    "service": service,
                    "count": 1,
                    "total_duration_ms": duration,
                    "max_duration_ms": duration,
                }
            else:
                group["count"] += 1
                group["total_duration_ms"] += duration
                if duration > group["max_duration_ms"]:
                    group["max_duration_ms"] = duration
    return [groups[name] for name in sorted(groups)]


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
PYEOF

chmod 644 /app/summarize.py
python -c "import ast,sys; ast.parse(open('/app/summarize.py', encoding='utf-8').read())"
