"""Directory discovery helpers."""

import os


def collect(root):
    """Yield (relative_path, absolute_path) for every regular file below root.

    The relative path always uses "/" separators so the manifest is stable
    regardless of the host platform.
    """
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            rel = os.path.relpath(full, root)
            results.append((rel.replace(os.sep, "/"), full))
    return results
