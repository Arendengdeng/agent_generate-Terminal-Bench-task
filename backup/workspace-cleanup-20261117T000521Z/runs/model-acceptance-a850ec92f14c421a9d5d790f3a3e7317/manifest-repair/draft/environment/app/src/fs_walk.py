"""目录遍历辅助函数。

注意：这里只负责“发现”文件，不读取文件内容。
"""

import os


def _join_rel(prefix, name):
    if not prefix:
        return name
    return prefix + "/" + name


def walk_files(root):
    """产出 (rel_path, abs_path) 二元组。

    rel_path 以 POSIX 分隔符表示，相对于 root。
    """
    results = []
    _walk(root, "", results, 0)
    return results


def _walk(root, prefix, results, depth):
    directory = os.path.join(root, prefix) if prefix else root
    try:
        entries = os.listdir(directory)
    except OSError:
        return
    for name in entries:
        abs_path = os.path.join(directory, name)
        rel_path = _join_rel(prefix, name)
        if os.path.isdir(abs_path):
            # 目录本身不进入清单，只继续向下发现文件。
            _walk(root, rel_path, results, depth + 1)
        else:
            results.append((rel_path, abs_path))
