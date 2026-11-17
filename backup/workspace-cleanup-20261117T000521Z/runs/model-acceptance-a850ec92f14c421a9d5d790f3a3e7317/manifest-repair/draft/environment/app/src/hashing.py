"""内容大小与摘要计算。"""

import hashlib

CHUNK_SIZE = 64 * 1024


def digest_file(path):
    """返回 (size, sha256_hex)。"""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        data = handle.read()
    size = len(data)
    hasher.update(data)
    return size, hasher.hexdigest()
