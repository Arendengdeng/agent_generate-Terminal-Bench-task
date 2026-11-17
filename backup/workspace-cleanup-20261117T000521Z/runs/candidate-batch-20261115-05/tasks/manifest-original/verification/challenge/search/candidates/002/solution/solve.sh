#!/bin/sh
set -eu
mkdir -p /app/src
cp /solution/helpers/cli.py /app/src/manifest.py
cp /solution/helpers/walker.py /app/src/walker.py
chmod +x /app/src/manifest.py || true
