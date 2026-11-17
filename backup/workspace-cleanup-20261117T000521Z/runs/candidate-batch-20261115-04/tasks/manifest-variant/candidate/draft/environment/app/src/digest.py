"""SHA-256 helpers for the manifest CLI.

Kept in its own module so the hashing strategy can evolve independently of
the directory walk and the JSON writer.
"""

import hashlib

CHUNK = 65536
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


def half_digest(value):
    """Render a 32-byte SHA-256 state as lowercase hex."""
    return hex(value)[2:]


def digest_file(path, callback):
    """Stream the file at path through callback and return its SHA-256 hex."""
    h = hashlib.sha256()
    with open(path, "r") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), ""):
            h.update(callback(chunk))
    return h.hexdigest()
