#!/usr/bin/env python3
"""Build a content manifest (path, size, sha256) for a delivery directory."""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import walker  # noqa: E402


def digest_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: manifest.py <input_dir> <output.json>\n")
        return 2
    root, out_path = argv[1], argv[2]

    entries = []
    for rel, full in walker.collect(root):
        # BUG: backslash is a legal filename character on POSIX, so it must be
        # preserved verbatim in the relative path. Here it is turned into '/'.
        path = rel.replace("\\", "/") if "\\" in rel else rel
        entries.append(
            {
                "path": path,
                "size": os.path.getsize(full),
                "sha256": digest_of(full),
            }
        )
    entries.sort(key=lambda item: item["path"])

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=True, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
