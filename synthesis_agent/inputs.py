import json
from .errors import SynthesisError
from .files import relative_path


def require_text(obj, keys):
    if not isinstance(obj, dict):
        raise SynthesisError("expected a JSON object")
    for key in keys:
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            raise SynthesisError(f"missing/non-string field: {key}")


def validate_inputs(plan, contract):
    require_text(plan, ["title", "category", "goal", "scenario"])
    if plan["category"] not in {"cli_repair", "code_repair"}:
        raise SynthesisError("UNSUPPORTED_DIRECTION: only Python CLI repair is supported")
    if not isinstance(plan.get("skills"), list) or not plan["skills"] or any(not isinstance(s, str) or not s.strip() for s in plan["skills"]):
        raise SynthesisError("skills must be a nonempty string list")
    # Legacy plans omit these fields; explicit conflicting declarations are rejected.
    for key, expected in {"language": "python", "environment": "linux-docker"}.items():
        if key in plan and plan[key] != expected:
            raise SynthesisError(f"UNSUPPORTED_DIRECTION: {key} must be {expected}")
    if 'task_kind' in plan and plan['task_kind'] not in {'cli_data_processing', 'cli_repair'}:
        raise SynthesisError('UNSUPPORTED_DIRECTION: task_kind must be cli_data_processing or cli_repair')
    require_text(contract, ["objective", "workspace", "command", "input_spec", "output_spec"])
    if contract["workspace"] != "/app" or not contract["command"].startswith(("python ", "python3 ")):
        raise SynthesisError("UNSUPPORTED_DIRECTION: requires a Python CLI in /app")
    deliverables = contract.get("deliverables")
    if not isinstance(deliverables, dict) or deliverables.get("allowed_dependencies") != "python-stdlib":
        raise SynthesisError("UNSUPPORTED_DEPENDENCIES: only python-stdlib is supported")
    if type(deliverables.get("allow_additional_files")) is not bool:
        raise SynthesisError("allow_additional_files must be boolean")
    paths = deliverables.get("artifact_paths")
    if not isinstance(paths, list) or not paths:
        raise SynthesisError("artifact_paths must be a nonempty list")
    normalized = []
    for path in paths:
        if not isinstance(path, str) or not path.startswith("/app/"):
            raise SynthesisError("artifact paths must be below /app")
        normalized.append(relative_path(path[5:]).casefold())
    if len(set(normalized)) != len(paths):
        raise SynthesisError("duplicate artifact paths")
    for path in normalized:
        if any(path.startswith(other + "/") for other in normalized if other != path):
            raise SynthesisError("overlapping artifact scopes")
    reqs = contract.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        raise SynthesisError("requirements must be nonempty")
    ids = []
    for req in reqs:
        require_text(req, ["id", "description"])
        ids.append(req["id"])
    if len(set(ids)) != len(ids):
        raise SynthesisError("requirement IDs must be unique")
    limits = contract.get("limits")
    if not isinstance(limits, dict) or "command_timeout_sec" not in limits:
        raise SynthesisError("limits.command_timeout_sec is required")
    if any(type(value) is not int or value <= 0 for value in limits.values()):
        raise SynthesisError("limits must be positive integers")


def in_scope(path, contract):
    d = contract["deliverables"]
    return any(path == p or (d["allow_additional_files"] and path.startswith(p + "/")) for p in d["artifact_paths"])


def instruction_appendix(contract):
    return "\n\n## 完成标准（Contract 原文）\n\n```json\n" + json.dumps(contract, ensure_ascii=False, indent=2) + "\n```\n"
