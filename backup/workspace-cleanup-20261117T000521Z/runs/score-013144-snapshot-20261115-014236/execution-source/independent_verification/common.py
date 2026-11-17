import hashlib
import json
from pathlib import Path

from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import FileSet, relative_path, safe_ancestors


def write_json(path, value):
    path = Path(path)
    safe_ancestors(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reports are written once by their owning stage.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def new_directory(path):
    path = safe_ancestors(Path(path).absolute())
    path.mkdir(parents=True, exist_ok=False)
    return path


def digest(files):
    return {name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in sorted(files.items())}


def validate_coverage(contract, coverage, nodeids):
    ids = {r["id"] for r in contract["requirements"]}
    if (not isinstance(nodeids, list) or not nodeids
            or any(not isinstance(n, str) or not n for n in nodeids)
            or len(set(nodeids)) != len(nodeids)):
        raise SynthesisError("collection must contain unique, nonempty test node IDs")
    if not isinstance(coverage, list):
        raise SynthesisError("coverage must be an array")
    seen = set()
    for row in coverage:
        if not isinstance(row, dict) or set(row) != {"requirement_id", "test_names"}:
            raise SynthesisError("invalid coverage row")
        rid, names = row["requirement_id"], row["test_names"]
        if not isinstance(rid, str) or rid not in ids or rid in seen:
            raise SynthesisError("unknown or duplicate requirement ID")
        if (not isinstance(names, list) or not names
                or any(not isinstance(n, str) or n not in nodeids for n in names)
                or len(names) != len(set(names))):
            raise SynthesisError("mapping must reference actual collected tests")
        seen.add(rid)
    if seen != ids:
        raise SynthesisError("every requirement must have a test mapping")


def test_path(path):
    relative_path(path)
    if (("/" not in path and path.startswith("test_") and path.endswith(".py"))
            or (path.startswith("fixtures/") and Path(path).suffix in {".txt", ".json", ".csv", ".jsonl"})):
        return path
    raise SynthesisError("write only test_*.py or fixtures/*.{txt,json,csv,jsonl}")


def bounded_files(values, config):
    if not isinstance(values, dict):
        raise SynthesisError("expected a relative-path to UTF-8 content mapping")
    files = FileSet(config)
    for name, content in values.items():
        files.put(name, content)
    return files
