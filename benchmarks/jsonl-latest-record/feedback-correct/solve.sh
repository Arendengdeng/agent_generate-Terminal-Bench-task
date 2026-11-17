#!/bin/sh
set -eu
cat > /app/latest.py <<'PYTHON_SOURCE'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    rows = [json.loads(line) for line in stream]
selected = {}
for _, row in sorted(enumerate(rows), key=lambda item: (item[1]["key"], item[1]["version"], item[0])):
    selected[row["key"]] = row
result = [selected[key] for key in sorted(selected)]
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False)
PYTHON_SOURCE
