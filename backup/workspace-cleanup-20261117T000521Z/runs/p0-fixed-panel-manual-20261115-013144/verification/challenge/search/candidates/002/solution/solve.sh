#!/bin/sh
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -d /app ]; then
  cp "$DIR/clean.py" /app/clean.py
  chmod 644 /app/clean.py 2>/dev/null || true
fi
