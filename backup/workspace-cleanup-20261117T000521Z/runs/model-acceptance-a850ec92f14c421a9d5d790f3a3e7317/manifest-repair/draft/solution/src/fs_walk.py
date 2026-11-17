"""目录递归遍历：发现 input_dir 下的全部普通文件。"""

import os

_PRUNE = {"__pycache__"}


def _join_rel(prefix, name):
    if not prefix:
        return name
    return prefix + "/" + name


def walk_files(root):
    """产出 (rel_path, abs_path)。

    rel_path 使用 ``/`` 分隔，相对于 root；只返回普通文件，
    空目录不会产生任何条目。结果不保证顺序。
    """
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            abs_path = os.path.join(dirpath, name)
            if not os.path.isfile(abs_path) or os.path.islink(abs_path):
                continue
            rel_path = os.path.relpath(abs_path, root).replace(os.sep, "/")
            results.append((rel_path, abs_path))
    return results


def relative_prefix(prefix, name):
    """拼接相对路径前缀（供其它模块复用）。"""
    return _join_rel(prefix, name)
