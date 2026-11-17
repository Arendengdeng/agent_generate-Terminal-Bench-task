"""Filesystem walking helpers for the manifest CLI."""

import os


def collect_files(root):
    """Yield (relative_path, absolute_path) for regular files under root.

    Relative paths use POSIX separators.
    """
    found = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isdir(full):
            for rel, abs_path in collect_files(full):
                found.append((name + "/" + rel, abs_path))
        elif os.path.isfile(full):
            found.append((name, full))
    return found


def sort_paths(paths):
    return paths.sort()
