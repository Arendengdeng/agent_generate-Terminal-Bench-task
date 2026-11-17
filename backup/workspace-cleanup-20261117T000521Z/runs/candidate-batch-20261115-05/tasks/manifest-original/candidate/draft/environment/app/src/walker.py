"""Directory discovery helpers."""

import os


def collect(root):
    """Yield (relative_path, absolute_path) for files below root."""
    results = []
    for name in os.listdir(root):
        full = os.path.join(root, name)
        if os.path.isfile(full):
            results.append((name, full))
    return results
