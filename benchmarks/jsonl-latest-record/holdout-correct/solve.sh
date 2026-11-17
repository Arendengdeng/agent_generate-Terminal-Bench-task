#!/bin/sh
set -eu
cat > /app/latest.py <<'PYTHON_SOURCE'
import json, sys
best = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        event = json.loads(line)
        key = event["key"]
        if key not in best or event["version"] >= best[key]["version"]:
            best[key] = event
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump([best[key] for key in sorted(best)], stream, ensure_ascii=False)
PYTHON_SOURCE
