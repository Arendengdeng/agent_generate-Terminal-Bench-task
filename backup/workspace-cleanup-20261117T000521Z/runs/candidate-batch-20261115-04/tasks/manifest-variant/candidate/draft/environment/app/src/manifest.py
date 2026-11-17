"""Directory manifest CLI.

Usage: python /app/src/manifest.py <input_dir> <output.json>

Walks the input directory recursively, groups every regular file by the
SHA-256 digest of its content and writes a JSON array with one object per
distinct digest: {"size": <bytes>, "sha256": <hex>, "paths": [<rel paths>]}.
"""

import json
import os
import sys

import digest
from walker import collect_files


def measure(path):
    """Return (size_bytes, sha256_hex) for a file path."""

    def identity(chunk):
        return chunk

    return os.path.getsize(path), digest.digest_file(path, identity)


def build_manifest(root):
    groups = {}
    for rel, full in collect_files(root):
        size, key = measure(full)
        groups.setdefault(key, []).append((rel, size))

    entries = []
    for digest_value in sorted(groups):
        members = groups[digest_value]
        entries.append({
            "size": members[0][1],
            "sha256": digest.half_digest(int(digest_value, 16)),
            "paths": [rel for rel, _ in members],
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
    with open(out_path, "w") as fh:
        json.dump(entries, fh, ensure_ascii=False)
        fh.write("\n")
    print("%d group(s) written to %s" % (len(entries), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
