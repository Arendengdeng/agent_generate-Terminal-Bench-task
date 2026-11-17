#!/bin/sh
# Install the replacement cleaner at the Contract artifact path.
set -e
mkdir -p /app
cp "$(dirname "$0")/helpers/cli.py" /app/clean.py
chmod 755 /app/clean.py
