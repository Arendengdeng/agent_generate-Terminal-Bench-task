#!/bin/sh
# Reference repair for the directory digest CLI.
# Runs from /app; the repaired sources live next to this script in /solution.
set -eu

mkdir -p /app/src
cp /solution/manifest.py /app/src/manifest.py
cp /solution/scanner.py /app/src/scanner.py
chmod 0644 /app/src/manifest.py /app/src/scanner.py
