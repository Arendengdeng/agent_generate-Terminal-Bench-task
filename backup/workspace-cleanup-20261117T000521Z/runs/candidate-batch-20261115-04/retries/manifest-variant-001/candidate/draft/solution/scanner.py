"""Helpers used by the manifest CLI to walk the input tree."""

import os


def collect_files(root):
    """Return every regular file below ``root`` (any depth).

    Directories themselves are never returned, so empty directories simply
    contribute nothing. Symlinks and special files are skipped. An explicit
    stack is used instead of recursion so deep trees are safe.
    """
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                children = list(entries)
        except FileNotFoundError:
            continue
        for entry in children:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                found.append(entry.path)
    found.sort()
    return found


def relative_posix_path(absolute_root, path):
    """Return ``path`` relative to ``absolute_root`` with POSIX separators."""
    rel = os.path.relpath(path, absolute_root)
    return rel.replace(os.sep, "/")
