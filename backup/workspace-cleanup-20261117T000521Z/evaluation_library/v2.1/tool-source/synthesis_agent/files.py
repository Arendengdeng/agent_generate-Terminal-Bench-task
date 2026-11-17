"""Portable paths and bounded, ordinary-file-only input/output. No archive extraction."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .errors import SynthesisError, BudgetExceeded


def relative_path(value):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise SynthesisError("expected a nonempty relative path of at most 240 characters")
    parts = value.split("/")
    for part in parts:
        if (part in {"", ".", ".."} or part.endswith((".", " "))
                or re.search(r'[\\:<>"|?*\x00-\x1f\x7f]', part)
                or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(?:\..*)?", part)):
            raise SynthesisError(f"unsafe path: {value!r}")
    return value


def assert_plain(path, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise SynthesisError(f"not an ordinary {'directory' if directory else 'file'}: {path}")
    if not directory and info.st_nlink != 1:
        raise SynthesisError(f"hard links are not accepted: {path}")
    return info


def safe_ancestors(path):
    path = Path(os.path.abspath(path))
    for parent in reversed((path, *path.parents)):
        try:
            assert_plain(parent, directory=True)
        except FileNotFoundError:
            pass
    return path


def read_regular(path, limit):
    path = Path(os.path.abspath(path))
    safe_ancestors(path.parent)
    original = assert_plain(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (original.st_dev, original.st_ino) != (opened.st_dev, opened.st_ino)):
            raise SynthesisError(f"input file changed or is not ordinary: {path}")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise BudgetExceeded(f"file exceeds {limit} bytes: {path}")
    return data


def read_json(path, limit=256_000):
    try:
        return json.loads(read_regular(path, limit).decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise SynthesisError(f"invalid JSON input: {path}") from exc


class FileSet:
    def __init__(self, config):
        self.config = config
        self.files = {}

    def put(self, path, content):
        relative_path(path)
        if not isinstance(content, str):
            raise SynthesisError("file content must be UTF-8 text")
        data = content.encode("utf-8")
        if len(data) > self.config.max_file_bytes:
            raise BudgetExceeded("file size budget exceeded")
        for other in self.files:
            for left, right in zip(other.split("/"), path.split("/")):
                if left.casefold() != right.casefold():
                    break
                if left != right:
                    raise SynthesisError("case alias in path components")
            if other != path and (other.casefold() == path.casefold()
                    or other.casefold().startswith(path.casefold() + "/")
                    or path.casefold().startswith(other.casefold() + "/")):
                raise SynthesisError("path alias or file/directory collision")
        if len(self.files) + (path not in self.files) > self.config.max_files:
            raise BudgetExceeded("file count budget exceeded")
        total = sum(len(v.encode("utf-8")) for k, v in self.files.items() if k != path) + len(data)
        if total > self.config.max_total_bytes:
            raise BudgetExceeded("total file size budget exceeded")
        self.files[path] = content

    def digest(self):
        return hashlib.sha256(json.dumps(self.files, sort_keys=True, ensure_ascii=True).encode()).hexdigest()

    def manifest(self):
        return {p: hashlib.sha256(s.encode()).hexdigest() for p, s in sorted(self.files.items())}

    def export(self, root):
        root = safe_ancestors(root)
        root.mkdir(exist_ok=True, parents=True)
        for name, content in sorted(self.files.items()):
            dest = root / relative_path(name)
            safe_ancestors(dest.parent)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(content.encode("utf-8"))
            if name.endswith(".sh"):
                dest.chmod(0o755)


def load_seed(root, config):
    result = FileSet(config)
    if root is None:
        return result
    root = safe_ancestors(root)
    assert_plain(root, directory=True)
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            assert_plain(Path(directory) / name, directory=True)
        for name in files:
            path = Path(directory) / name
            try:
                content = read_regular(path, config.max_file_bytes).decode("utf-8")
            except UnicodeError as exc:
                raise SynthesisError("seed supports UTF-8 text files only") from exc
            result.put(path.relative_to(root).as_posix(), content)
    return result
