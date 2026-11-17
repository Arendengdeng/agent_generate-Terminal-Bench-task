#!/bin/sh
# Reference repair: rewrite the manifest modules under /app/src.
set -eu

here=$(dirname "$0")

cp "$here/src/walker.py" /app/src/walker.py
cp "$here/src/digest.py" /app/src/digest.py
cp "$here/src/groups.py" /app/src/groups.py
cp "$here/src/manifest.py" /app/src/manifest.py

python -B -c 'import ast, glob, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding="utf-8")) for p in glob.glob("/app/src/*.py")]'
