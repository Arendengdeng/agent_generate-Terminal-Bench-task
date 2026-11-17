#!/bin/sh
# 参考解：用修复后的模块覆盖 /app/src 下的实现。
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p /app/src
rm -f /app/src/*.py
rm -rf /app/src/__pycache__
cp "$HERE/src/__init__.py" /app/src/__init__.py
cp "$HERE/src/fs_walk.py" /app/src/fs_walk.py
cp "$HERE/src/hashing.py" /app/src/hashing.py
cp "$HERE/src/paths.py" /app/src/paths.py
cp "$HERE/src/manifest.py" /app/src/manifest.py
find /app/src -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
