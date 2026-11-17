#!/usr/bin/env python3
"""Merge JSONL config events into the latest per-key snapshot.

Usage:
    python latest.py <input.jsonl> <output.json>

Each input line is a JSON object with fields key (non-empty string),
version (non-negative int) and value (string). The output is a JSON
array with one record per key: the record with the highest version for
that key; when several records share that highest version, the one
appearing last in the input wins. Records are sorted by key.
"""

import json
import sys


def load_events(path):
    events = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def merge(events):
    latest = {}
    for event in events:
        key = event["key"]
        version = event["version"]
        current = latest.get(key)
        if current is None or version > _as_number(current["version"]):
            latest[key] = {
                "key": key,
                "version": version,
                "value": event["value"],
            }
    return [latest[key] for key in sorted(latest)]


def _as_number(value):
    # Normalise versions before comparison so that mixed inputs still rank.
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return -1


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: latest.py <input.jsonl> <output.json>\n")
        return 2
    events = load_events(argv[1])
    records = merge(events)
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
