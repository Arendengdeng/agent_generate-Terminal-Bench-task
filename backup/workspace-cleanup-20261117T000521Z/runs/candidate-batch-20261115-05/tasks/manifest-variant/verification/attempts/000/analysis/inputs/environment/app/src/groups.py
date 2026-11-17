"""Group file digests into manifest entries."""

import digest
import walker


def build_manifest(root):
    """Return a list of manifest entries for all regular files below root."""
    groups = {}
    sizes = {}
    for relative, absolute in walker.iter_files(root):
        size, sha = digest.digest_file(absolute)
        groups.setdefault(sha, []).append(relative)
        sizes[sha] = size

    entries = []
    for sha, paths in groups.items():
        entries.append({
            "size": sizes[sha],
            "sha256": sha,
            "paths": paths,
        })
    return entries
