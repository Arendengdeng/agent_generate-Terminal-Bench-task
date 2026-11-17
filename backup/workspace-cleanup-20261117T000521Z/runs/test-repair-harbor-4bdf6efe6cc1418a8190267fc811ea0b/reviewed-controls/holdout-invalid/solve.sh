#!/bin/sh
set -eu
cat > /app/clean.py <<'PY'
print(-1)
PY
