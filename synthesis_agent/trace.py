"""Credential-safe JSONL records and bounded observation summaries."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote


def provenance():
    """Record source content even when Git metadata is unavailable or dirty."""
    root = Path(__file__).resolve().parents[1]
    source = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for package in ('synthesis_agent', 'independent_verification')
              for p in sorted((root / package).rglob('*.py'))}
    result = {'source_digest': hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()}
    for key, args in [('git_commit', ['rev-parse', 'HEAD']), ('git_status', ['status', '--short'])]:
        try:
            proc = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=10)
            result[key] = proc.stdout.strip() if proc.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            result[key] = None
    result['dirty'] = bool(result['git_status']) if result['git_status'] is not None else None
    return result


def run_identity(output):
    """Identify canonical experiment output, including nested verification stages."""
    path = Path(output).absolute()
    for index, part in enumerate(path.parts):
        if part == 'runs' and index + 2 < len(path.parts):
            return {'experiment_id': path.parts[index + 1], 'run_id': path.parts[index + 2]}
    return {'experiment_id': None, 'run_id': path.name}


def redact(value, api_key=""):
    if isinstance(value, dict):
        return {redact(k, api_key): (
            "[REDACTED]" if re.fullmatch(
                r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)", str(k))
            else redact(v, api_key)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, api_key) for v in value]
    if not isinstance(value, str):
        return value
    if api_key:
        for secret in (api_key, quote(api_key, safe=""), json.dumps(api_key)[1:-1]):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)\bBearer\s+[^\s\"',;}]+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(
        r'''(?ix)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)\b["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',
        r"\1[REDACTED]", value)
    value = re.sub(r"https?://[^\s\"'<>]+",
                   lambda m: "[REDACTED URL]" if "@" in m[0] or "?" in m[0] else m[0], value)
    return value


def summarize(value, limit=2000):
    """Summarize already-redacted strings, preserving structured result fields."""
    if isinstance(value, dict):
        return {k: summarize(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [summarize(v, limit) for v in value]
    if isinstance(value, str) and len(value) > limit:
        return {"preview": value[:limit], "truncated": True, "characters": len(value),
                "redacted_sha256": hashlib.sha256(value.encode()).hexdigest()}
    return value
