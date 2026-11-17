"""Directory discovery helpers."""

import os


def collect(root):
    """Yield (relative_path, absolute_path) for every regular file below root."""
    results = []
    stack = [(root, "")]
    while stack:
        full_dir, rel_dir = stack.pop()
        try:
            with os.scandir(full_dir) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            rel = entry.name if not rel_dir else rel_dir + "/" + entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append((entry.path, rel))
                elif entry.is_file(follow_symlinks=False):
                    results.append((rel, entry.path))
            except OSError:
                continue
    results.sort(key=lambda item: item[0])
    return results
