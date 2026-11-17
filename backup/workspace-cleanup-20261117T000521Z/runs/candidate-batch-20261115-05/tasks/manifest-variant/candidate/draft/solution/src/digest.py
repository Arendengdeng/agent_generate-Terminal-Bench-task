"""Content digest helpers for the manifest CLI."""

import hashlib

CHUNK_SIZE = 65536


def digest_file(path):
    """Return (size, lowercase hex sha256) for the file at path."""
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
