"""Recursive walker for the manifest CLI."""

import os


def iter_files(root):
    """Yield (relative_path, absolute_path) pairs for regular files below root.

    Directories are skipped, relative paths always use POSIX separators, and
    traversal order is deterministic.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        for name in filenames:
            absolute = os.path.join(dirpath, name)
            if os.path.islink(absolute):
                continue
            if not os.path.isfile(absolute):
                continue
            relative = os.path.relpath(absolute, root)
            yield relative.replace(os.sep, "/"), absolute
