#!/bin/sh
set -e
mkdir -p /app
cp "$(dirname "$0")/clean.py" /app/clean.py
chmod 755 /app/clean.py
