"""Recursive walker for the manifest CLI (work in progress)."""

import os


def iter_files(root):
    """Yield (relative_path, absolute_path) pairs for regular files below root.

    NOTE: only the top level of the tree is visited right now, and the
    directory listing order is whatever the filesystem hands back.
    """
    for name in os.listdir(root):
        absolute = os.path.join(root, name)
        if os.path.isdir(absolute):
            continue
        relative = name.replace(os.sep, "/")
        yield relative, absolute
