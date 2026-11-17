"""Directory digest CLI.

Scans a directory tree, groups regular files with identical content and
writes a JSON manifest describing every group.

This is the original prototype. It was written for the flat sample folder
that used to live next to it and only reads text files one level deep.
"""

import hashlib
import json
import os
import sys

CHUNK = 8192
TEXT_ENCODING = "utf-8"


def scan_dir(root):
    """Return the regular files found directly inside ``root``."""
    found = []
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if os.path.isfile(full):
            found.append(full)
    return found


def digest_file(path):
    """Return the hex SHA-256 and byte size of ``path``."""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "r", encoding=TEXT_ENCODING) as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            payload = chunk.encode(TEXT_ENCODING)
            size += len(payload)
            hasher.update(payload)
    return hasher.hexdigest(), size


def relative_posix_path(absolute_root, path):
    rel = os.path.relpath(path, absolute_root)
    return rel.replace(os.sep, "/")


def group_files(root):
    absolute_root = os.path.abspath(root)
    groups = {}
    for path in scan_dir(root):
        digest_hex, size = digest_file(path)
        rel = relative_posix_path(absolute_root, path)
        group = groups.get(digest_hex)
        if group is None:
            group = {"size": size, "sha256": digest_hex, "paths": []}
            groups[digest_hex] = group
        group["paths"].append(rel)
    result = [groups[key] for key in sorted(groups)]
    for group in result:
        group["paths"].sort()
    return result


def main(argv):
    if len(argv) != 3:
        print("usage: manifest.py <input_dir> <output.json>", file=sys.stderr)
        return 2
    input_dir, output_path = argv[1], argv[2]
    if not os.path.isdir(input_dir):
        print("not a directory: %s" % input_dir, file=sys.stderr)
        return 2
    groups = group_files(input_dir)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(groups, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
