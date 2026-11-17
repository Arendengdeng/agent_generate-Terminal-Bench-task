"""Group file digests into manifest entries."""

import digest
import walker


def build_manifest(root):
    """Return a list of manifest entries for all regular files below root.

    Entries are grouped by SHA-256, paths within a group are sorted with plain
    Python string ordering, and the entry list itself is sorted by SHA-256.
    """
    groups = {}
    sizes = {}
    for relative, absolute in walker.iter_files(root):
        size, sha = digest.digest_file(absolute)
        groups.setdefault(sha, []).append(relative)
        sizes[sha] = size

    entries = []
    for sha in sorted(groups):
        entries.append({
            "size": sizes[sha],
            "sha256": sha,
            "paths": sorted(groups[sha]),
        })
    return entries
