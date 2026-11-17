#!/bin/sh
set -eu
cat > /app/clean.py <<'PY'
import sys; sys.stdout.write(str(6 * 7) + chr(10))
PY
