#!/bin/sh
# Repair /app/summarize.py by installing the corrected implementation.
set -eu
cp /solution/summarize.py /app/summarize.py
chmod 0644 /app/summarize.py
