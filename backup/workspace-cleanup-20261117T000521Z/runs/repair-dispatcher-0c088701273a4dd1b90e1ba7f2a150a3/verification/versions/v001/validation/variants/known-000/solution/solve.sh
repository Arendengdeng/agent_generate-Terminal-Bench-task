#!/bin/sh
set -eu
cat > /app/clean.py <<'PY'
print(42)
PY
