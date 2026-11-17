#!/bin/sh
# Reference fix: install the repaired cleaner into /app.
set -e
cp /solution/clean.py /app/clean.py
chmod 644 /app/clean.py
