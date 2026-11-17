#!/bin/sh
# Reference repair: install the corrected cleaner into /app.
set -eu
cp /solution/clean.py /app/clean.py
chmod +x /app/clean.py
exit 0
