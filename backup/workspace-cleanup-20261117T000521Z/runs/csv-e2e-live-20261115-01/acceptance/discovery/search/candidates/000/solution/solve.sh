#!/bin/sh
# Installs the replacement CLI at the Contract artifact path.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
mkdir -p /app
cp "$DIR/clean.py" /app/clean.py
chmod 755 /app/clean.py
