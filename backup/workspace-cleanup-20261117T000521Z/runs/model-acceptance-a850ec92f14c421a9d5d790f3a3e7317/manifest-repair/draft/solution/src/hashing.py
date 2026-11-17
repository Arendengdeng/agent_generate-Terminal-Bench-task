"""按二进制内容计算大小与 SHA-256。"""

import hashlib

CHUNK_SIZE = 64 * 1024


def digest_file(path):
    """以二进制方式读取文件，返回 (size, sha256_hex)。"""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    return size, hasher.hexdigest()
