#!/bin/sh
# Repaired implementation of the directory manifest CLI.
set -eu

cat > /app/src/walker.py <<'PY'
"""Filesystem walking helpers for the manifest CLI."""

import os


def collect_files(root):
    """Return (relative_posix_path, absolute_path) pairs for regular files.

    Directories are traversed recursively; symlinks and special files are
    skipped. The result is sorted by relative path.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found.append((rel, full))
    found.sort(key=lambda item: item[0])
    return found


def sort_paths(paths):
    """Return a new list of paths sorted by Python string order."""
    return sorted(paths)
PY

cat > /app/src/digest.py <<'PY'
"""SHA-256 helpers for the manifest CLI."""

import hashlib

CHUNK = 65536
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


def digest_file(path, callback):
    """Stream the raw bytes of path through callback, returning the SHA-256 hex."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(callback(chunk))
    return h.hexdigest()
PY

cat > /app/src/manifest.py <<'PY'
"""Directory manifest CLI.

Usage: python /app/src/manifest.py <input_dir> <output.json>

Walks the input directory recursively, groups every regular file by the
SHA-256 digest of its binary content and writes a UTF-8 JSON array with one
object per distinct digest: {"size": <bytes>, "sha256": <hex>, "paths": [...]}.
"""

import json
import os
import sys

import digest
from walker import collect_files


def measure(path):
    """Return (size_in_bytes, sha256_hex) for the file at path."""

    def identity(chunk):
        return chunk

    return os.path.getsize(path), digest.digest_file(path, identity)


def build_manifest(root):
    """Return manifest entries sorted by ascending sha256."""
    groups = {}
    for rel, full in collect_files(root):
        size, key = measure(full)
        groups.setdefault(key, []).append((rel, size))

    entries = []
    for digest_value in sorted(groups):
        members = groups[digest_value]
        entries.append({
            "size": members[0][1],
            "sha256": digest_value,
            "paths": sorted(rel for rel, _ in members),
        })
    return entries


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: manifest.py <input_dir> <output.json>\n")
        return 2
    root, out_path = argv[1], argv[2]
    if not os.path.isdir(root):
        sys.stderr.write("error: not a directory: %s\n" % root)
        return 1

    entries = build_manifest(root)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("%d group(s) written to %s" % (len(entries), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY
