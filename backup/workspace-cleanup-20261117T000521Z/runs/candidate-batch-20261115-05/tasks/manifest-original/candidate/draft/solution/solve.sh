#!/bin/sh
# Repair the manifest CLI: recursive POSIX-relative paths and binary SHA-256.
set -eu

SRC=/app/src
HERE=$(cd "$(dirname "$0")" && pwd)

cp "$HERE/manifest.py" "$SRC/manifest.py"
cp "$HERE/walker.py" "$SRC/walker.py"
chmod 0644 "$SRC/manifest.py" "$SRC/walker.py"
