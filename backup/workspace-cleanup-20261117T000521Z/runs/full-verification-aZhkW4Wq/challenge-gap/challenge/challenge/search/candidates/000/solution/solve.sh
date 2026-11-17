#!/bin/sh
# Required solution entrypoint: install the deliverable artifact.
set -e
HERE=$(dirname "$0")
chmod 755 "$HERE/app/clean.py" 2>/dev/null || true
if [ -d /app ]; then
    cp "$HERE/app/clean.py" /app/clean.py
    chmod 755 /app/clean.py
fi
